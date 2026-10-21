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
) -> bool:
    """Should the integration ask the car for fresh data now?

    Only while charging, never while a command is still pending, not more often
    than ``interval_minutes`` and not when the data is already younger than half
    of that (something else, e.g. an automation, just refreshed it).
    """
    if interval_minutes <= 0 or not is_charging(car) or command_pending(car):
        return False
    now = now or datetime.now(timezone.utc)
    if last_sent is not None and (now - last_sent).total_seconds() < interval_minutes * 60 - 5:
        return False
    age = data_age_minutes(car, now)
    if age is not None and age < interval_minutes / 2:
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
