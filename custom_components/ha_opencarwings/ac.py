"""A/C state: what the user asked for, until the car reports it.

The car reports its A/C state (``ev_info.ac_status``) only when it sends a data packet, which can be minutes after
a command. The Android app shows a spinner meanwhile; a Home Assistant switch cannot, and one that jumps back to
its old position after a click looks broken. So after a command the switch keeps the requested position and
follows the car again when

* the server pushes an A/C alert for the car (4 = on, 5 = off, 7 = finished by timer or unexpectedly),
* the command fails (the server reports an error or a timeout, or alert 97), or
* ``HOLD_SECONDS`` have passed (a remote A/C run lasts about that long).

When the car sent nothing at all for that long, the controller asks it once ("Refresh data") so the real state
shows up. All of this is bookkeeping on data the integration already receives; the car is contacted only for
the A/C command itself and for that single check.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .freshness import command_pending, data_timestamp

_LOGGER = logging.getLogger(__name__)

HOLD_SECONDS = 15 * 60

MIN_TEMP_C = 16
MAX_TEMP_C = 31
DEFAULT_TEMP_C = 21

ALERT_AC_ON = 4
ALERT_AC_OFF = 5
ALERT_AC_FINISHED = 7
ALERT_AC_ERROR = 97

COMMAND_AC_ON = 3
COMMAND_AC_OFF = 4
# Result codes of ``command_result`` on the server.
RESULT_ERRORS = (1, 2)


def clamp_temperature(value: Any) -> int:
    """A whole number of degrees Celsius the server accepts (16-31)."""
    try:
        degrees = round(float(value))
    except (TypeError, ValueError):
        return DEFAULT_TEMP_C
    return max(MIN_TEMP_C, min(MAX_TEMP_C, degrees))


def start_payload(car: Any, degrees: Any) -> dict | None:
    """Command 3 payload with the target temperature, for TCUs that take one (Ficosa 2016, like the app).

    Always in Celsius (``unit`` 0): the server validates the value against 31, so a Fahrenheit value (60 and up)
    would be rejected and the car would start with its own default. Home Assistant converts the number for display.
    """
    tcu_type = getattr(car, "tcu_type", None)
    if str(getattr(tcu_type, "value", tcu_type)) != "ficosa2016":
        return None
    return {"unit": 0, "temp": clamp_temperature(degrees)}


class AcController:
    """Per-account bookkeeping for the A/C switch and the temperature number."""

    def __init__(self, hass: Any, entry_id: str, *, hold_seconds: int = HOLD_SECONDS) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._hold = timedelta(seconds=hold_seconds)
        self._hold_seconds = hold_seconds
        self._desired: dict[str, tuple[bool, datetime]] = {}
        self._temperature: dict[str, int] = {}
        self._tasks: dict[str, Any] = {}

    # -- temperature -------------------------------------------------------
    def temperature(self, vin: str) -> int:
        return self._temperature.get(vin, DEFAULT_TEMP_C)

    def set_temperature(self, vin: str, value: Any) -> None:
        self._temperature[vin] = clamp_temperature(value)

    # -- requested state ---------------------------------------------------
    def desired(self, vin: str, now: datetime | None = None) -> bool | None:
        """The position the switch should keep, or None when it should follow the car."""
        held = self._desired.get(vin)
        if held is None:
            return None
        value, since = held
        if (now or datetime.now(timezone.utc)) - since >= self._hold:
            return None
        return value

    def request(self, vin: str, on: bool, *, check: bool = True, now: datetime | None = None) -> None:
        """Remember what the user asked for; ``check`` also schedules the one-off look at the car."""
        since = now or datetime.now(timezone.utc)
        self._desired[vin] = (on, since)
        self._cancel(vin)
        if check:
            self._tasks[vin] = self._hass.async_create_task(self._check_later(vin, since))
        self._notify()

    def clear(self, vin: str) -> None:
        self._desired.pop(vin, None)
        self._cancel(vin)
        self._notify()

    def cancel_all(self) -> None:
        for vin in list(self._tasks):
            self._cancel(vin)

    # -- events from the car ----------------------------------------------
    def handle_alert(self, data: dict) -> None:
        """An alert pushed by the server. A/C alerts settle the switch at once."""
        car = data.get("car") if isinstance(data, dict) else None
        vin = car.get("vin") if isinstance(car, dict) else None
        kind = data.get("type") if isinstance(data, dict) else None
        if not vin:
            return
        if kind == ALERT_AC_ON:
            self.request(vin, True, check=False)
        elif kind in (ALERT_AC_OFF, ALERT_AC_FINISHED):
            self.request(vin, False, check=False)
        elif kind == ALERT_AC_ERROR:
            self.clear(vin)
            self._tell_failed(vin, data.get("additional_data") or data.get("type_display"))

    def command_finished(self, vin: str, command_type: int, car: Any) -> None:
        """The server reported a result for our A/C command; on failure the switch goes back to the car's state."""
        if car is None or getattr(car, "command_type", command_type) not in (COMMAND_AC_ON, COMMAND_AC_OFF):
            return
        if getattr(car, "command_result", 0) in RESULT_ERRORS:
            self.clear(vin)
            self._tell_failed(vin, getattr(car, "command_result_display", None))

    # -- internals ---------------------------------------------------------
    def _cancel(self, vin: str) -> None:
        task = self._tasks.pop(vin, None)
        if task is not None and hasattr(task, "cancel"):
            task.cancel()

    def _notify(self) -> None:
        from . import DOMAIN

        coordinator = self._hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("coordinator")
        updater = getattr(coordinator, "async_update_listeners", None)
        if updater is not None:
            updater()

    def _latest_car(self, vin: str) -> Any:
        from . import DOMAIN

        coordinator = self._hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("coordinator")
        for car in getattr(coordinator, "data", None) or []:
            if car.vin == vin:
                return car.get_latest_car()
        return None

    async def _check_later(self, vin: str, since: datetime) -> None:
        """After the hold: if the car sent nothing since the command, ask it once; then follow the car again."""
        try:
            await asyncio.sleep(self._hold_seconds)
            held = self._desired.get(vin)
            if held is None or held[1] != since:
                return  # settled by an alert, or replaced by a newer command
            car = self._latest_car(vin)
            heard_since, _ = data_timestamp(car)
            if car is not None and (heard_since is None or heard_since < since) and not command_pending(car):
                _LOGGER.info("No report from %s since the A/C command; asking the car once", vin)
                from . import DOMAIN
                from .charging_refresh import send_refresh

                await send_refresh(self._hass.data[DOMAIN][self._entry_id], vin)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - network
            _LOGGER.exception("Checking on the car after the A/C command failed")
        finally:
            if self._desired.get(vin, (None, None))[1] == since:
                self._desired.pop(vin, None)
            if self._tasks.get(vin) is asyncio.current_task():
                self._tasks.pop(vin, None)
            self._notify()

    def _tell_failed(self, vin: str, reason: Any) -> None:
        _LOGGER.warning("A/C command for %s failed: %s", vin, reason)
        try:
            from homeassistant.components import persistent_notification

            persistent_notification.async_create(
                self._hass,
                f"The A/C command for {vin} did not succeed ({reason or 'no reason given'}). "
                "The switch shows the car's real state again.",
                title="OpenCARWINGS: A/C command failed",
                notification_id=f"ha_opencarwings_ac_failed_{vin}",
            )
        except Exception:  # noqa: BLE001 - notification is a courtesy
            _LOGGER.debug("Could not create the A/C failure notification", exc_info=True)
