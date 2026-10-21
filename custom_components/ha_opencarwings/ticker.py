"""Re-write an entity's state every minute so time-based values (age) stay current."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.core import callback


def track_minute(entity) -> None:
    """Call from ``async_added_to_hass``; the listener is removed with the entity."""
    from homeassistant.helpers.event import async_track_time_interval

    @callback
    def _tick(_now) -> None:
        entity.async_write_ha_state()

    entity.async_on_remove(async_track_time_interval(entity.hass, _tick, timedelta(minutes=1)))
