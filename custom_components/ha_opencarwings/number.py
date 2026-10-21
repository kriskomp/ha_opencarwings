"""Number platform: the temperature the A/C is started with."""
from __future__ import annotations

from typing import Any, List

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        CONFIG = "config"

from . import DOMAIN
from .ac import DEFAULT_TEMP_C, MAX_TEMP_C, MIN_TEMP_C, clamp_temperature, start_payload
from .util import CarData


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars: List[CarData] = data.get("cars", [])
    controller = data.get("ac")

    entities = []
    unsupported: list[str] = []
    for car in cars:
        if not car.vin:
            continue
        ent = CarACTemperatureNumber(entry.entry_id, car, coordinator, controller)
        # Only TCUs that take a temperature with the A/C command (the Android app shows its slider for them only).
        if start_payload(car.get_latest_car(), DEFAULT_TEMP_C) is not None:
            entities.append(ent)
        else:
            unsupported.append(ent.unique_id)
    if unsupported:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        for unique_id in unsupported:
            entity_id = registry.async_get_entity_id("number", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)
    async_add_entities(entities)


class CarACTemperatureNumber(CoordinatorEntity, RestoreNumber):
    """Target temperature for "A/C on". Shown in the user's unit system; the server always gets Celsius."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "°C"
    _attr_native_min_value = MIN_TEMP_C
    _attr_native_max_value = MAX_TEMP_C
    _attr_native_step = 1
    _attr_icon = "mdi:thermometer"

    def __init__(self, entry_id: str, car: CarData, coordinator=None, controller=None) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._entry_id = entry_id
        self._seed_car = car
        self._vin = car.vin
        self._controller = controller
        self._fallback = DEFAULT_TEMP_C

    @property
    def _car(self) -> CarData:
        for car in getattr(self.coordinator, "data", None) or []:
            if car.vin == self._vin:
                return car
        return self._seed_car

    @property
    def name(self) -> str:
        return f"{self._car.car_model_data().get('name', None) or 'Car'} A/C Temperature"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_ac_temperature_{self._vin}"

    @property
    def device_info(self) -> dict[str, Any]:
        return self._car.car_model_data()

    @property
    def native_value(self) -> float:
        if self._controller is not None:
            return self._controller.temperature(self._vin)
        return self._fallback

    async def async_set_native_value(self, value: float) -> None:
        # Home Assistant converts a value typed in °F back to °C; the server takes whole degrees.
        degrees = clamp_temperature(value)
        if self._controller is not None:
            self._controller.set_temperature(self._vin, degrees)
        else:
            self._fallback = degrees
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None and self._controller is not None:
            self._controller.set_temperature(self._vin, last.native_value)
