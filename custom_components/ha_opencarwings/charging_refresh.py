"""Periodic "Refresh data" command while the car is charging.

The OpenCARWINGS REST API cannot set the server-side ``periodic_refresh`` (the
field is not writable through ``PATCH /api/car/<vin>/``), so the integration does
it itself: every ``charging_refresh_interval`` minutes it sends command 1 to cars
whose last known state is "charging", then follows the command until the server
reports a result (success, error or timeout).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import opencarwings_client
from opencarwings_client import ApiCommandCreateRequest

from .freshness import COMMAND_REFRESH, command_pending, refresh_due

_LOGGER = logging.getLogger(__name__)

POLL_SECONDS = 15
# The server marks a command as timed out after a few minutes; give it room.
POLL_TIMEOUT_SECONDS = 8 * 60


def store_car(coordinator: Any, vin: str, car_detail: Any) -> bool:
    """Put a fresher ``Car`` into the coordinator data and notify listeners."""
    data = getattr(coordinator, "data", None)
    if not data:
        return False
    for car in data:
        if car.vin == vin:
            car.car_detail = car_detail
            setter = getattr(coordinator, "async_set_updated_data", None)
            if setter is not None:
                setter(data)
            else:  # pragma: no cover - minimal test stubs
                for listener in list(getattr(coordinator, "_listeners", [])):
                    listener()
            return True
    return False


async def follow_command(client: Any, coordinator: Any, vin: str, *, poll_seconds: int = POLL_SECONDS,
                         timeout_seconds: int = POLL_TIMEOUT_SECONDS) -> Any:
    """Poll the car until the server reports a result for the pending command.

    Every poll goes into the coordinator, so "Command Status", "Data Age" and the
    sensors follow the command. Returns the last ``Car`` read (None on failure).
    """
    cars_api = opencarwings_client.CarsApi(client)
    waited = 0
    car = None
    while waited < timeout_seconds:
        await asyncio.sleep(poll_seconds)
        waited += poll_seconds
        car = await cars_api.api_car_read(vin)
        store_car(coordinator, vin, car)
        if not command_pending(car):
            _LOGGER.debug("Command for %s finished: %s", vin, getattr(car, "command_result_display", None))
            return car
    _LOGGER.warning("Command for %s still pending after %s s", vin, waited)
    return car


class ChargingRefresh:
    """Sends refresh commands to charging cars on a fixed interval."""

    def __init__(self, hass: Any, entry_id: str, interval_minutes: int) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self.interval_minutes = interval_minutes
        self._last_sent: dict[str, datetime] = {}
        self._running: dict[str, asyncio.Task] = {}

    def _entry_data(self) -> dict:
        from . import DOMAIN

        return self._hass.data.get(DOMAIN, {}).get(self._entry_id, {})

    async def async_tick(self, now: datetime | None = None) -> None:
        """Called every ``interval_minutes`` by the time tracker."""
        data = self._entry_data()
        coordinator = data.get("coordinator")
        if coordinator is None:
            return
        # The charging flag we decide on is only as new as the last poll.
        try:
            await coordinator.async_request_refresh()
        except Exception:  # pragma: no cover - network
            _LOGGER.exception("Could not refresh car data before the charging refresh check")
        now = now or datetime.now(timezone.utc)
        for car_data in list(coordinator.data or []):
            vin = car_data.vin
            if not vin or vin in self._running:
                continue
            car = car_data.get_latest_car()
            if refresh_due(
                car,
                last_sent=self._last_sent.get(vin),
                interval_minutes=self.interval_minutes,
                now=now,
            ):
                self._last_sent[vin] = now
                self._running[vin] = self._hass.async_create_task(self._async_cycle(vin))

    async def _async_cycle(self, vin: str) -> None:
        try:
            client = self._entry_data()["client"]
            coordinator = self._entry_data().get("coordinator")
            cars_api = opencarwings_client.CarsApi(client)
            response = await cars_api.api_command_create(
                vin, ApiCommandCreateRequest(command_type=COMMAND_REFRESH)
            )
            store_car(coordinator, vin, response.car)
            await follow_command(client, coordinator, vin)
        except Exception:  # pragma: no cover - network
            _LOGGER.exception("Charging refresh for %s failed", vin)
        finally:
            self._running.pop(vin, None)
