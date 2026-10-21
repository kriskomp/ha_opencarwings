"""What this version removes, moves to diagnostics, or keeps out of the recorder."""
from types import SimpleNamespace

import pytest

import custom_components.ha_opencarwings as init_mod
import custom_components.ha_opencarwings.button as button_mod
import custom_components.ha_opencarwings.sensor as sensor_mod
from tests.helpers import car_data, make_car


def test_removed_entities_are_really_gone():
    for name in ("CarListSensor", "CarLastRequestedSensor", "CarVehicleHealthSensor"):
        assert not hasattr(sensor_mod, name)
    assert not hasattr(button_mod, "OpenCarWingsRefreshButton")


@pytest.mark.asyncio
async def test_sensor_setup_creates_no_account_level_sensor():
    car = car_data(make_car())
    hass = SimpleNamespace(data={init_mod.DOMAIN: {"e1": {"coordinator": SimpleNamespace(data=[car]), "cars": [car]}}})
    added = []
    await sensor_mod.async_setup_entry(hass, SimpleNamespace(entry_id="e1", options={}, data={}), added.extend)
    unique_ids = [e.unique_id for e in added]
    assert all(uid.endswith("_VIN1") for uid in unique_ids)          # nothing per account
    assert "ha_opencarwings_last_requested_VIN1" not in unique_ids   # the removed timestamp sensor
    assert "ha_opencarwings_last_requested_command_VIN1" in unique_ids  # the command name sensor stays
    assert not any("veh_health" in uid for uid in unique_ids)


def test_fixed_facts_about_the_car_are_diagnostic():
    specs = {s.key: s for s in sensor_mod.CAR_SENSORS}
    assert specs["obc_6kw_avail"].diagnostic and specs["batt_heater_avail"].diagnostic
    assert not specs["soc"].diagnostic and not specs["batt_heater_status"].diagnostic
    coord = SimpleNamespace(data=[car_data(make_car())], _listeners=[])
    ent = sensor_mod.CarValueSensor(coord, "e1", "VIN1", specs["obc_6kw_avail"], seed_car=coord.data[0])
    assert ent._attr_entity_category == sensor_mod.EntityCategory.DIAGNOSTIC
    ent = sensor_mod.CarValueSensor(coord, "e1", "VIN1", specs["soc"], seed_car=coord.data[0])
    assert getattr(ent, "_attr_entity_category", None) is None


def test_raw_car_stays_out_of_the_recorder():
    assert "raw_car" in sensor_mod.CarStatusSensor._unrecorded_attributes
    # everything else on the Status sensor is still recorded
    assert sensor_mod.CarStatusSensor._unrecorded_attributes == frozenset({"raw_car"})


def test_every_command_button_has_a_material_design_icon():
    for cls in button_mod.CAR_BUTTONS:
        icon = cls._attr_icon
        assert icon.startswith("mdi:"), cls
    assert button_mod.CarDoorLockButton._attr_icon == "mdi:lock-open-variant"   # command 7 unlocks
    assert button_mod.CarDoorUnLockButton._attr_icon == "mdi:lock"              # command 8 locks


def test_safety_poll_is_half_an_hour_and_the_number_platform_is_loaded():
    assert init_mod.SAFETY_POLL_MIN == 30
    assert "number" in init_mod.PLATFORMS
