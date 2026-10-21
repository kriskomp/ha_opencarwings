"""Switch platform to control car climate (A/C) as a simple switch."""
from __future__ import annotations

from typing import Any, List
import logging

import opencarwings_client
from opencarwings_client import ApiClient, ApiCommandCreateRequest, CommandResponse

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .charging_refresh import follow_command, store_car
from .commands import command_supported
from .util import CarData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars: List[CarData] = data.get("cars", [])

    entities = []
    for car in cars:
        if car.vin:
            ent = CarACSwitch(entry.entry_id, car, coordinator)
            # Tests call entity methods directly; set hass here for testability
            ent.hass = hass
            entities.append(ent)

    async_add_entities(entities)


class CarACSwitch(CoordinatorEntity, SwitchEntity):
    """Represents the car A/C as a switch. Follows the coordinator, like the other entities."""

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._entry_id = entry_id
        self._seed_car = car
        self._vin = car.vin
        # state: True = on, False = off (no real-time state unless refreshed)
        self._is_on = False

    @property
    def _car(self) -> CarData:
        # A refresh replaces the CarData objects; never keep the one from setup.
        for car in getattr(self.coordinator, "data", None) or []:
            if car.vin == self._vin:
                return car
        return self._seed_car

    @property
    def name(self) -> str:
        return f"{self._car.car_model_data().get("name", None) or 'Car'} A/C"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_ac_{self._vin}"

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def available(self) -> bool:
        """Unavailable only when the car's TCU does not support A/C on/off.

        A pending command does not grey the switch out: a command can stay pending for minutes while
        the car sleeps, and a switch stuck grey for that long looks broken.
        """
        car_data = self._car.get_latest_car()
        return (
            car_data is not None
            and command_supported(car_data, 3)
            and command_supported(car_data, 4)
        )

    @property
    def device_info(self) -> dict[str, Any]:
        return self._car.car_model_data()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn A/C on by sending command_type 3 to `/api/command/{vin}/`."""
        client = hass_client(self.hass, self._entry_id)
        try:
            cars_api = opencarwings_client.CarsApi(client)
            command_result: CommandResponse = await cars_api.api_command_create(self._vin, ApiCommandCreateRequest(
                command_type=3
            ))
            try:
                coordinator = self.hass.data[DOMAIN][self._entry_id].get("coordinator")
                store_car(coordinator, self._vin, command_result.car)
                self.hass.async_create_task(follow_command(client, coordinator, self._vin))
            except Exception:  # pragma: no cover - coordinator failure
                _LOGGER.exception("Failed to update coordinator data after A/C command for %s", self._vin)

        except Exception:  # pragma: no cover - network
            _LOGGER.exception("Failed to turn A/C on for %s", self._vin)
            raise

    async def async_turn_off(self, **kwargs) -> None:
        """Turn A/C off by sending command_type 4."""
        client = hass_client(self.hass, self._entry_id)
        try:
            cars_api = opencarwings_client.CarsApi(client)
            command_result: CommandResponse = await cars_api.api_command_create(self._vin, ApiCommandCreateRequest(
                command_type=4
            ))
            try:
                coordinator = self.hass.data[DOMAIN][self._entry_id].get("coordinator")
                store_car(coordinator, self._vin, command_result.car)
                self.hass.async_create_task(follow_command(client, coordinator, self._vin))
            except Exception:  # pragma: no cover - coordinator failure
                _LOGGER.exception("Failed to update coordinator data after A/C command for %s", self._vin)

        except Exception:  # pragma: no cover - network
            _LOGGER.exception("Failed to turn A/C off for %s", self._vin)
            raise


def hass_client(hass, entry_id: str) -> ApiClient:
    """Helper to get the API client stored in hass.data."""
    return hass.data[DOMAIN][entry_id]["client"]
