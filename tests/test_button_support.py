from types import SimpleNamespace

import pytest

import custom_components.ha_opencarwings.button as button_mod
from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings.commands import command_supported
from custom_components.ha_opencarwings.switch import CarACSwitch
from homeassistant.helpers import entity_registry as er_stub
from tests.helpers import car_data, make_car

# What the server reports for a Ficosa 2016 TCU (the Leaf): no "Charge start 80%" (6).
FICOSA = [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]


def _car(supported):
    car = make_car()
    if supported is not None:
        car.supported_commands = supported
    return car


def test_command_supported():
    assert command_supported(_car(FICOSA), 7) is True
    assert command_supported(_car(FICOSA), 6) is False
    assert command_supported(_car([1, 2, 3, 4, 5]), 13) is False
    assert command_supported(_car(None), 6) is True  # unknown list: do not hide anything
    assert command_supported(None, 6) is True


def test_door_buttons_match_the_server_command_ids():
    # server: 7 = Door unlock, 8 = Door lock
    cd = car_data(_car(FICOSA))
    unlock = button_mod.CarDoorLockButton("e1", cd)
    lock = button_mod.CarDoorUnLockButton("e1", cd)
    assert (unlock._command_id, unlock.name) == (7, "Unlock Doors for Leaf")
    assert (lock._command_id, lock.name) == (8, "Lock Doors for Leaf")


@pytest.mark.asyncio
async def test_setup_creates_only_supported_buttons_and_removes_stale_ones():
    car = car_data(_car(FICOSA))
    coordinator = SimpleNamespace(data=[car])
    hass = SimpleNamespace(data={DOMAIN: {"e1": {"coordinator": coordinator, "cars": [car]}}})
    entry = SimpleNamespace(entry_id="e1")
    er_stub.reset()
    er_stub.add("button.leaf_charge_start_80_for_leaf", "e1", unique_id="ha_opencarwings_car_chargestart80_VIN1")
    er_stub.add("button.leaf_horn_for_leaf", "e1", unique_id="ha_opencarwings_car_horn_VIN1")
    added = []

    await button_mod.async_setup_entry(hass, entry, added.extend)

    names = [e.name for e in added]
    assert "Charge start 80% for Leaf" not in names
    assert "Horn for Leaf" in names and "Request data refresh for Leaf" in names
    assert er_stub.REGISTRY.removed == ["button.leaf_charge_start_80_for_leaf"]


def test_button_is_unavailable_when_the_command_is_not_supported():
    btn = button_mod.CarChargeStart80Button("e1", car_data(_car(FICOSA)))
    assert btn.available is False
    assert button_mod.CarHornButton("e1", car_data(_car(FICOSA))).available is True


def test_ac_switch_availability_depends_only_on_support():
    assert CarACSwitch("e1", car_data(_car(FICOSA))).available is True
    assert CarACSwitch("e1", car_data(_car([1, 2]))).available is False
    pending = make_car(command_requested=True)
    pending.supported_commands = FICOSA
    assert CarACSwitch("e1", car_data(pending)).available is True  # pending command: not grey


def test_ac_switch_follows_the_coordinator_data():
    coordinator = SimpleNamespace(data=[car_data(_car([1, 2]))])
    switch = CarACSwitch("e1", coordinator.data[0], coordinator)
    assert switch.available is False
    coordinator.data = [car_data(_car(FICOSA))]  # a refresh replaces the objects
    assert switch.available is True
