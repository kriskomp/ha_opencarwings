"""Reading integration options (options override the data saved at setup)."""
from __future__ import annotations

from typing import Any

# Showing the car on the map is what the integration always did; keep it on by default.
DEFAULT_TRACK_LOCATION = True


def get_option(entry: Any, key: str, default: Any) -> Any:
    options = getattr(entry, "options", None) or {}
    data = getattr(entry, "data", None) or {}
    return options.get(key, data.get(key, default))


def track_location_enabled(entry: Any) -> bool:
    return bool(get_option(entry, "track_location", DEFAULT_TRACK_LOCATION))
