"""Switch platform to control car climate (A/C) as a simple switch."""
from __future__ import annotations

from typing import Any, List
import logging

import opencarwings_client
from opencarwings_client import ApiClient, ApiCommandCreateRequest, CommandResponse

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN
from .ac import COMMAND_AC_OFF, COMMAND_AC_ON, start_payload
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
    """The car's A/C. On means the car reports A/C running.

    Right after a command the switch keeps the position the user chose (see ``ac.py``) instead of jumping back
    until the car has reported; it follows the car again on the server's A/C alert, on failure, or after 15 minutes.
    """

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._entry_id = entry_id
        self._seed_car = car
        self._vin = car.vin

    @property
    def _car(self) -> CarData:
        # A refresh replaces the CarData objects; never keep the one from setup.
        for car in getattr(self.coordinator, "data", None) or []:
            if car.vin == self._vin:
                return car
        return self._seed_car

    def _controller(self):
        hass = getattr(self, "hass", None)
        if hass is None:
            return None
        return hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("ac")

    @property
    def name(self) -> str:
        return f"{self._car.car_model_data().get('name', None) or 'Car'} A/C"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_ac_{self._vin}"

    @property
    def is_on(self) -> bool:
        controller = self._controller()
        held = controller.desired(self._vin) if controller is not None else None
        if held is not None:
            return held
        car = self._car.get_latest_car()
        ev = getattr(car, "ev_info", None)
        return bool(getattr(ev, "ac_status", False))

    @property
    def icon(self) -> str:
        return "mdi:fan" if self.is_on else "mdi:fan-off"

    @property
    def available(self) -> bool:
        """Unavailable only when the car's TCU does not support A/C on/off.

        A pending command does not grey the switch out: a command can stay pending for minutes while
        the car sleeps, and a switch stuck grey for that long looks broken.
        """
        car_data = self._car.get_latest_car()
        return (
            car_data is not None
            and command_supported(car_data, COMMAND_AC_ON)
            and command_supported(car_data, COMMAND_AC_OFF)
        )

    @property
    def device_info(self) -> dict[str, Any]:
        return self._car.car_model_data()

    async def async_turn_on(self, **kwargs) -> None:
        """Start A/C: command 3, with the target temperature for TCUs that take one."""
        controller = self._controller()
        payload = None
        if controller is not None:
            payload = start_payload(self._car.get_latest_car(), controller.temperature(self._vin))
        await self._send(COMMAND_AC_ON, True, payload)

    async def async_turn_off(self, **kwargs) -> None:
        """Stop A/C: command 4."""
        await self._send(COMMAND_AC_OFF, False)

    async def _send(self, command: int, on: bool, payload: dict | None = None) -> None:
        client = hass_client(self.hass, self._entry_id)
        controller = self._controller()
        if controller is not None:
            controller.request(self._vin, on)  # keep the chosen position while the car answers
        try:
            cars_api = opencarwings_client.CarsApi(client)
            command_result: CommandResponse = await cars_api.api_command_create(self._vin, ApiCommandCreateRequest(
                command_type=command,
                command_payload=payload,
            ))
        except Exception:  # pragma: no cover - network
            _LOGGER.exception("Failed to send A/C command %s for %s", command, self._vin)
            if controller is not None:
                controller.clear(self._vin)
            raise
        try:
            coordinator = self.hass.data[DOMAIN][self._entry_id].get("coordinator")
            store_car(coordinator, self._vin, command_result.car)
            self.hass.async_create_task(self._follow(client, coordinator, command))
        except Exception:  # pragma: no cover - coordinator failure
            _LOGGER.exception("Failed to update coordinator data after A/C command for %s", self._vin)

    async def _follow(self, client, coordinator, command: int) -> None:
        car = await follow_command(client, coordinator, self._vin)
        controller = self._controller()
        if controller is not None:
            controller.command_finished(self._vin, command, car)


def hass_client(hass, entry_id: str) -> ApiClient:
    """Helper to get the API client stored in hass.data."""
    return hass.data[DOMAIN][entry_id]["client"]
