"""Button platform: command buttons per car and a diagnostic "Reconnect" for the live connection."""
from __future__ import annotations

import logging

import opencarwings_client
from opencarwings_client import ApiClient, ApiCommandCreateRequest, CommandResponse

from homeassistant.components.button import ButtonEntity
from typing import Any, List

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

from . import DOMAIN
from .charging_refresh import follow_command, store_car
from .commands import command_supported
from .util import CarData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")

    entities: List[OpenCarwingsButton] = []

    # Per-car command buttons, only for commands the car's TCU supports (the API says which)
    cars: List[CarData] = data.get("cars", [])
    unsupported_ids: list[str] = []
    for car in cars:
        if not car.vin:
            continue
        for cls in CAR_BUTTONS:
            ent = cls(entry.entry_id, car, coordinator=coordinator)
            if ent.command_supported():
                entities.append(ent)
            else:
                unsupported_ids.append(ent.unique_id)
    await async_remove_unsupported(hass, entry, unsupported_ids)

    # One "Reconnect" for the account's live connection, on the first car's device (diagnostic section)
    ws = data.get("websocket")
    first = next((car for car in cars if car.vin), None)
    if ws is not None and first is not None:
        entities.append(OpenCarWingsReconnectButton(entry.entry_id, first, ws, coordinator=coordinator))

    # Tests set hass on the entity for direct method calls
    for ent in entities:
        ent.hass = hass

    async_add_entities(entities)

async def async_remove_unsupported(hass, entry, unique_ids: list[str]) -> None:
    """Drop registry entries of buttons the car cannot do (left over from earlier versions)."""
    if not unique_ids:
        return
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for entity in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if entity.domain == "button" and getattr(entity, "unique_id", None) in unique_ids:
            registry.async_remove(entity.entity_id)


def hass_client(hass, entry_id: str) -> ApiClient:
    """Helper to get the API client stored in hass.data."""
    return hass.data[DOMAIN][entry_id]["client"]

class OpenCarwingsButton(ButtonEntity):

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        self._entry_id = entry_id
        self._car = car
        self._vin = car.vin
        self._coordinator = coordinator



    @property
    def device_info(self) -> dict[str, Any]:
        return self._car.car_model_data()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"entry_id": self._entry_id, "vin": self._vin}

class OpenCarWingsCommandButton(OpenCarwingsButton):

    def __init__(self, command_id: int, entry_id: str, car: CarData, coordinator=None, command_payload: dict|None = None, command_pin: str|None = None) -> None:
        super().__init__(entry_id, car, coordinator)
        self._command_id = command_id
        self._command_payload = command_payload
        self._command_pin = command_pin

    def command_supported(self) -> bool:
        return command_supported(self._car.get_latest_car(), self._command_id)

    @property
    def available(self) -> bool:
        """Home Assistant greys the button out when the car's TCU does not support the command."""
        return self.command_supported()

    async def async_press(self) -> None:
        """Press the button to send a 'Refresh data' command to the API for this car."""
        client = hass_client(self.hass, self._entry_id)
        cars_api = opencarwings_client.CarsApi(client)
        try:
            command_result: CommandResponse = await cars_api.api_command_create(self._vin, ApiCommandCreateRequest(
                command_type=self._command_id,
                command_payload=self._command_payload,
                command_pin=self._command_pin
            ))
            try:
                store_car(self._coordinator, self._vin, command_result.car)
                # Follow the command so "Command Status" and the data age update
                # as soon as the car answers (or the server gives up).
                self.hass.async_create_task(
                    follow_command(hass_client(self.hass, self._entry_id), self._coordinator, self._vin)
                )
            except Exception:  # pragma: no cover - coordinator failure
                _LOGGER.exception("Failed to update coordinator data after command for %s", self._vin)
        except Exception:  # pragma: no cover - network
            _LOGGER.exception("Failed to request data refresh for %s", self._vin)
            raise

class OpenCarWingsReconnectButton(OpenCarwingsButton):
    """Diagnostic: close the live connection and open a new one (like F5 on the OpenCARWINGS web page).

    It talks to the server only; it never wakes the car. The connection is shared by all cars of the account,
    so there is one of these, on the first car's device.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:connection"

    def __init__(self, entry_id: str, car: CarData, ws, coordinator=None) -> None:
        super().__init__(entry_id, car, coordinator)
        self._ws = ws

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Reconnect live updates for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_reconnect_{self._entry_id}"

    async def async_press(self) -> None:
        await self._ws.async_reconnect()


class CarRefreshButton(OpenCarWingsCommandButton):
    """Button that sends a 'Refresh data' command for a specific car."""

    _attr_icon = "mdi:car-connected"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(1, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Request data refresh for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_refresh_{self._vin}"


class CarChargeStartButton(OpenCarWingsCommandButton):
    """Button that sends a 'Charge start' command for a specific car."""

    _attr_icon = "mdi:flash"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(2, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Charge start for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_chargestart_{self._vin}"

class CarChargeStart80Button(OpenCarWingsCommandButton):
    """Button that sends a 'Charge start 80%' command for a specific car."""

    _attr_icon = "mdi:battery-charging-80"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(6, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Charge start 80% for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_chargestart80_{self._vin}"

class CarDoorLockButton(OpenCarWingsCommandButton):
    """Command 7 = "Door unlock" on the server (the class and unique id keep their old, swapped names)."""

    _attr_icon = "mdi:lock-open-variant"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(7, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Unlock Doors for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_doorlock_{self._vin}"

class CarDoorUnLockButton(OpenCarWingsCommandButton):
    """Command 8 = "Door lock" on the server."""

    _attr_icon = "mdi:lock"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(8, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Lock Doors for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_doorunlock_{self._vin}"

class CarHornButton(OpenCarWingsCommandButton):

    _attr_icon = "mdi:bullhorn"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(9, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Horn for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_horn_{self._vin}"

class CarLightsButton(OpenCarWingsCommandButton):

    _attr_icon = "mdi:car-light-high"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(10, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Lights for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_lights_{self._vin}"

class CarHornAndLightsButton(OpenCarWingsCommandButton):

    _attr_icon = "mdi:car-light-alert"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(11, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Horn & Lights for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_horn_lights_{self._vin}"

class CarStopHornAndLightsButton(OpenCarWingsCommandButton):

    _attr_icon = "mdi:bullhorn-variant-outline"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(12, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Stop Horn & Lights for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_stop_horn_lights_{self._vin}"

class CarRemoteStartButton(OpenCarWingsCommandButton):

    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(13, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Remote Start for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_remote_start_{self._vin}"

class CarRemoteStopButton(OpenCarWingsCommandButton):

    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, entry_id: str, car: CarData, coordinator=None) -> None:
        super().__init__(14, entry_id, car, coordinator)

    @property
    def name(self) -> str:
        car_instance = self._car.get_latest_car()
        # Friendly label: prefer car nickname, then model name, then VIN
        label = (car_instance.nickname or self._vin) if car_instance is not None else self._vin
        return f"Remote Stop for {label}"

    @property
    def unique_id(self) -> str:
        return f"ha_opencarwings_car_remote_stop_{self._vin}"

CAR_BUTTONS = [
    CarRefreshButton,
    CarChargeStartButton,
    CarChargeStart80Button,
    CarDoorLockButton,
    CarDoorUnLockButton,
    CarHornButton,
    CarLightsButton,
    CarHornAndLightsButton,
    CarStopHornAndLightsButton,
    CarRemoteStartButton,
    CarRemoteStopButton,
]
