"""Helpers that answer "how old is the data we hold, and did the car answer?".

The generated API client marks ``ev_info.last_updated``, ``last_connection`` and
``command_request_time`` as read-only, and ``Model.to_dict()`` drops read-only
fields. Everything here therefore reads the model attributes directly instead of
going through ``to_dict()``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

COMMAND_REFRESH = 1
DEFAULT_FRESH_MINUTES = 30
# A "Refresh data" command the server still lists as waiting after this long is treated as unanswered: the
# integration asks again. The default is the server's own timeout (``LEAF_COMMAND_TIMEOUT``, 5 minutes); the
# option "Ask again after N seconds without an answer" lets the user shorten it (e.g. 120).
DEFAULT_COMMAND_TIMEOUT_SECONDS = 300
# The car says it is driving, but its last data packet is older than this: nobody has confirmed it for a while.
# Option "Driving without confirmation after N minutes".
DEFAULT_DRIVING_STALE_MINUTES = 20


def as_datetime(value: Any) -> datetime | None:
    """Return an aware datetime for a datetime or an ISO 8601 string, else None."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def data_timestamp(car: Any) -> tuple[datetime | None, str | None]:
    """When the car last sent a data packet, and which field said so.

    ``ev_info.last_updated`` is set by the server every time an EV-info packet
    arrives from the car. ``last_connection`` is the fallback (the car's TCU
    connected, not necessarily with fresh battery data).
    """
    if car is None:
        return None, None
    ts = as_datetime(getattr(getattr(car, "ev_info", None), "last_updated", None))
    if ts is not None:
        return ts, "ev_info.last_updated"
    ts = as_datetime(getattr(car, "last_connection", None))
    if ts is not None:
        return ts, "last_connection"
    return None, None


def data_age_minutes(car: Any, now: datetime | None = None) -> float | None:
    ts, _ = data_timestamp(car)
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max((now - ts).total_seconds() / 60.0, 0.0)


def is_fresh(age_minutes: float | None, threshold_minutes: float) -> bool:
    return age_minutes is not None and age_minutes <= threshold_minutes


def is_charging(car: Any) -> bool:
    """True while the last known state is "charging" (not just plugged in)."""
    ev = getattr(car, "ev_info", None)
    if ev is None:
        return False
    if getattr(ev, "charge_finish", None):
        return False
    return bool(getattr(ev, "charging", None) or getattr(ev, "quick_charging", None))


def command_pending(car: Any) -> bool:
    return bool(getattr(car, "command_requested", None))


def command_stalled(car: Any, now: datetime | None = None, stall_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> bool:
    """A pending "Refresh data" the car has not answered for ``stall_seconds``.

    Only refreshes count: another pending command (A/C, doors) must not be overwritten on the server.
    """
    if car is None or not command_pending(car) or getattr(car, "command_type", None) != COMMAND_REFRESH:
        return False
    requested = as_datetime(getattr(car, "command_request_time", None))
    if requested is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - requested).total_seconds() >= stall_seconds


def command_blocks(car: Any, now: datetime | None = None, stall_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> bool:
    """Is a command in progress that should keep us from sending another one?"""
    return command_pending(car) and not command_stalled(car, now, stall_seconds)


def command_summary(car: Any) -> dict[str, Any]:
    """The state of the last command sent to the car, from the API only."""
    if car is None:
        return {}
    request_time = as_datetime(getattr(car, "command_request_time", None))
    result = getattr(car, "command_result_display", None)
    command_type = getattr(car, "command_type", None)
    confirmed = (
        request_time
        if command_type == COMMAND_REFRESH
        and not command_pending(car)
        and getattr(car, "command_result", None) == 0
        else None
    )
    return {
        "command_type": command_type,
        "command_type_display": getattr(car, "command_type_display", None),
        "command_result": getattr(car, "command_result", None),
        "command_result_display": result,
        "command_requested": command_pending(car),
        "command_request_time": request_time,
        "last_confirmed_refresh": confirmed,
    }


def refresh_due(
    car: Any,
    *,
    last_sent: datetime | None,
    interval_minutes: int,
    now: datetime | None = None,
    stall_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> bool:
    """Should the integration ask the car for fresh data now?

    Only while charging, never while a command is still pending, not more often
    than ``interval_minutes`` and not when the data is already younger than half
    of that (something else, e.g. an automation, just refreshed it).
    """
    now = now or datetime.now(timezone.utc)
    if interval_minutes <= 0 or not is_charging(car) or command_blocks(car, now, stall_seconds):
        return False
    if last_sent is not None and (now - last_sent).total_seconds() < interval_minutes * 60 - 5:
        return False
    age = data_age_minutes(car, now)
    if age is not None and age < interval_minutes / 2:
        return False
    return True


def is_running(car: Any) -> bool:
    """True while the car reports that it is driving."""
    return bool(getattr(getattr(car, "ev_info", None), "car_running", None))


def driving_unconfirmed(car: Any, now: datetime | None = None, stale_minutes: float = DEFAULT_DRIVING_STALE_MINUTES) -> bool:
    """``car_running`` is on, but the car has sent no data packet for ``stale_minutes``.

    The server only clears "driving" when the car sends a packet with the ignition off. A car that was parked
    without the end-of-trip report (the driver did not agree on the navigation screen) stays "driving" forever.
    """
    if not is_running(car):
        return False
    age = data_age_minutes(car, now)
    return age is not None and age > stale_minutes


def is_driving(car: Any, now: datetime | None = None, stale_minutes: float = DEFAULT_DRIVING_STALE_MINUTES) -> bool:
    return is_running(car) and not driving_unconfirmed(car, now, stale_minutes)


def last_contact(car: Any) -> datetime | None:
    """The newest sign of life from the car: the later of ``ev_info.last_updated`` and ``last_connection``."""
    if car is None:
        return None
    stamps = [
        as_datetime(getattr(getattr(car, "ev_info", None), "last_updated", None)),
        as_datetime(getattr(car, "last_connection", None)),
    ]
    stamps = [t for t in stamps if t is not None]
    return max(stamps) if stamps else None


def idle_refresh_due(
    car: Any,
    *,
    interval_minutes: int,
    now: datetime | None = None,
    stall_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    stale_minutes: float = DEFAULT_DRIVING_STALE_MINUTES,
) -> bool:
    """Should a parked car be asked for fresh data (a "check on the car" command)?

    Mirrors the server's own periodic refresh and protects the 12 V battery, because every command wakes
    the car's modem:

    * never while charging or driving (the car reports by itself, charging has its own option); a "driving"
      the car has not confirmed for a long time does not count as driving,
    * never while a command is pending (an unanswered refresh older than the timeout does not count),
    * only when the car has not been heard from for ``interval_minutes``,
    * and not when any command was requested within the last ``interval_minutes``. That also stops
      repeated wake-ups of a car that did not answer (timeout/error) and survives a Home Assistant restart.
    """
    if interval_minutes <= 0 or car is None:
        return False
    now = now or datetime.now(timezone.utc)
    if is_charging(car) or is_driving(car, now, stale_minutes) or command_blocks(car, now, stall_seconds):
        return False
    limit = interval_minutes * 60
    heard = last_contact(car)
    if heard is not None and (now - heard).total_seconds() < limit:
        return False
    requested = as_datetime(getattr(car, "command_request_time", None))
    if requested is not None and (now - requested).total_seconds() < limit:
        return False
    return True


def format_local(value: datetime | None) -> str | None:
    """Short local format ``dd.mm.yyyy HH:MM`` for attributes and cards."""
    if value is None:
        return None
    try:
        from homeassistant.util import dt as dt_util

        value = dt_util.as_local(value)
    except Exception:  # pragma: no cover - minimal test stubs
        pass
    return value.strftime("%d.%m.%Y %H:%M")


def fresh_threshold(entry: Any) -> int:
    """Minutes after which data counts as stale (option ``data_fresh_minutes``)."""
    options = getattr(entry, "options", None) or {}
    data = getattr(entry, "data", None) or {}
    try:
        return int(options.get("data_fresh_minutes", data.get("data_fresh_minutes", DEFAULT_FRESH_MINUTES)))
    except (TypeError, ValueError):
        return DEFAULT_FRESH_MINUTES


def format_minutes(minutes: Any) -> str | None:
    """Minutes as text: ``37 min``, ``2 h 30 min``, ``1 d 3 h``. None for a missing value."""
    if minutes is None:
        return None
    try:
        total = int(round(float(minutes)))
    except (TypeError, ValueError):
        return None
    if total < 0:
        return None
    days, rest = divmod(total, 1440)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if mins or not parts:
        parts.append(f"{mins} min")
    return " ".join(parts)


def driving_check_due(
    car: Any,
    *,
    last_sent: datetime | None,
    interval_minutes: int,
    now: datetime | None = None,
    stall_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> bool:
    """Should a car that reports "driving" be asked whether it still is?

    While it really drives the 12 V battery is charged, so a question every few minutes is harmless. When the
    car has stopped without a report, the answer (ignition off) corrects the server's state. Same pacing as the
    charging refresh: not more often than ``interval_minutes`` and not when the data is already fresh.
    """
    if interval_minutes <= 0 or not is_running(car):
        return False
    now = now or datetime.now(timezone.utc)
    if command_blocks(car, now, stall_seconds):
        return False
    if last_sent is not None and (now - last_sent).total_seconds() < interval_minutes * 60 - 5:
        return False
    age = data_age_minutes(car, now)
    return age is None or age >= interval_minutes / 2
