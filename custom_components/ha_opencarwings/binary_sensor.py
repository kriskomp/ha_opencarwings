"""Binary sensor: is the data we hold recent enough to trust?"""
from __future__ import annotations

from typing import Any, List

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from . import DOMAIN
from .freshness import data_age_minutes, data_timestamp, format_local, fresh_threshold, is_fresh
from .ticker import track_minute
from .util import CarData


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars: List[CarData] = coordinator.data if coordinator and coordinator.data is not None else data.get("cars", [])
    threshold = fresh_threshold(entry)
    async_add_entities(
        [CarDataFreshBinarySensor(coordinator, entry.entry_id, car.vin, threshold, seed_car=car) for car in cars if car.vin]
    )


class CarDataFreshBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """On while the car's last data packet is not older than the freshness threshold."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, vin: str, threshold_minutes: int, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._vin = vin
        self._threshold = threshold_minutes
        self._seed_car = seed_car
        self._attr_unique_id = f"ha_opencarwings_data_fresh_{vin}"

    def _get_car(self) -> CarData:
        for car in getattr(self.coordinator, "data", None) or []:
            if car.vin == self._vin:
                return car
        return self._seed_car or CarData(self._vin)

    @property
    def name(self) -> str:
        car = self._get_car().get_latest_car()
        prefix = (getattr(car, "nickname", None) if car is not None else None) or "Car"
        return f"{prefix} Data Fresh"

    @property
    def device_info(self) -> dict[str, Any]:
        return self._get_car().car_model_data()

    @property
    def is_on(self) -> bool:
        return is_fresh(data_age_minutes(self._get_car().get_latest_car()), self._threshold)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self._get_car().get_latest_car()
        ts, source = data_timestamp(car)
        age = data_age_minutes(car)
        return {
            "threshold_minutes": self._threshold,
            "age_minutes": None if age is None else int(age),
            "last_data_time": format_local(ts),
            "source": source,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        track_minute(self)
