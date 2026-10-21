from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.ha_opencarwings import sensor as sensor_mod
from custom_components.ha_opencarwings.button import CarDoorLockButton, CarDoorUnLockButton
from tests.helpers import car_data, make_car


def _sensor(cls, last_update=None):
    coord = SimpleNamespace(data=[car_data(make_car())], last_update_time=last_update, _listeners=[])
    return cls(coord, "e1", "VIN1", seed_car=coord.data[0])


def test_last_requested_is_a_native_timestamp():
    when = datetime(2026, 10, 21, 8, 59, 13, 106914, tzinfo=timezone.utc)
    ent = _sensor(sensor_mod.CarLastRequestedSensor, when)
    assert ent._attr_device_class == sensor_mod.SensorDeviceClass.TIMESTAMP
    assert ent.native_value == when


def test_last_requested_is_unknown_before_the_first_read():
    assert _sensor(sensor_mod.CarLastRequestedSensor).native_value is None


def test_data_age_is_a_duration_in_minutes():
    ent = _sensor(sensor_mod.CarDataAgeSensor)
    assert ent._attr_device_class == sensor_mod.SensorDeviceClass.DURATION
    assert ent._attr_native_unit_of_measurement == "min"


def test_charge_time_sensors_use_minutes():
    specs = {s.key: s for s in sensor_mod.CAR_SENSORS}
    for key in ("full_chg_time", "limit_chg_time", "obc_6kw"):
        assert specs[key].unit_of_measurement == "min"


def test_lock_and_unlock_buttons_have_distinct_names():
    car = car_data(make_car())
    assert CarDoorLockButton("e1", car).name == "Lock Doors for Leaf"
    assert CarDoorUnLockButton("e1", car).name == "Unlock Doors for Leaf"


def test_tracker_has_a_car_icon():
    from custom_components.ha_opencarwings.device_tracker import CarTracker

    assert CarTracker._attr_icon == "mdi:car"
