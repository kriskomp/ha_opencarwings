from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType

try:
    from homeassistant.components.device_tracker.config_entry import TrackerEntity
except Exception:  # pragma: no cover - tests running without hass stubs
    class TrackerEntity:  # type: ignore
        """Fallback base class used when TrackerEntity cannot be imported in tests."""
        pass

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .freshness import as_datetime, format_local
from .options import track_location_enabled
from .util import CarData



async def async_remove_tracker_entities(hass, entry) -> None:
    """Remove the device trackers of this entry from the entity registry."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for entity in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if entity.domain == "device_tracker":
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass, entry, async_add_entities):
    # Option "Show the car on the map": off means no tracker entity at all
    if not track_location_enabled(entry):
        await async_remove_tracker_entities(hass, entry)
        return

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")

    # If we have a coordinator, prefer its data; ensure it's primed before use
    cars = data.get("cars", [])
    if coordinator:
        if getattr(coordinator, "data", None) is None and hasattr(coordinator, "async_request_refresh"):
            try:
                await coordinator.async_request_refresh()
            except Exception:  # pragma: no cover - network
                pass
        cars = getattr(coordinator, "data", None) or cars

    # Only create trackers for cars with a VIN
    entities = [CarTracker(entry.entry_id, car, coordinator) for car in cars if car.vin]
    # Tests call entity methods directly; set hass on the entities for testability
    for ent in entities:
        ent.hass = hass
    async_add_entities(entities)

class CarTracker(CoordinatorEntity, TrackerEntity):
    """GPS position of the car. Follows the coordinator, so it moves when the data does."""

    _attr_icon = "mdi:car"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._entry_id = entry_id
        self._seed_car = car
        self._vin = car.vin

    @property
    def _car(self) -> CarData:
        for car in getattr(self.coordinator, "data", None) or []:
            if car.vin == self._vin:
                return car
        return self._seed_car

    @property
    def name(self) -> str:
        # Prefer the car nickname, then model name, then a fallback that includes the VIN
        car_instance = self._car.get_latest_car()
        if car_instance is not None:
            return f"{car_instance.nickname or f'Car {self._vin}'} Tracker"
        return f"{self._vin} Tracker"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_tracker_{self._vin}"

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    def _get_lat_lon(self):
        # Look for various forms of last location in the car data.
        car_instance = self._car.get_latest_car()

        if car_instance is not None and car_instance.location is not None:
            lat = car_instance.location.lat
            lon = car_instance.location.lon
            if lat is not None and lon is not None:
                # Accept commas as decimal separators ("53,0")
                try:
                    lat_f = float(str(lat).replace(",", "."))
                    lon_f = float(str(lon).replace(",", "."))
                    return lat_f, lon_f
                except Exception:
                    return None, None

        return None, None

    @property
    def latitude(self) -> float | None:
        return self._get_lat_lon()[0]

    @property
    def longitude(self) -> float | None:
        return self._get_lat_lon()[1]

    @property
    def available(self) -> bool:
        lat, lon = self._get_lat_lon()
        return lat is not None and lon is not None

    @property
    def location_name(self) -> str | None:
        # TODO reverse geolocate address
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Expose VIN and basic car data so it's visible on the entity, and
        # provide the raw last location under a single key for callers that
        # want to inspect the original payload.
        latest_car = self._car.get_latest_car()
        location = getattr(latest_car, "location", None)
        if location is None:
            return {}
        attrs = location.to_dict()
        # last_updated is read-only in the API model, so to_dict() drops it
        attrs["last_updated"] = format_local(as_datetime(getattr(location, "last_updated", None)))
        return attrs

    @property
    def device_info(self) -> dict[str, Any]:
        return self._car.car_model_data()
