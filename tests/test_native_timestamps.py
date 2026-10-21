from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.ha_opencarwings import sensor as sensor_mod
from custom_components.ha_opencarwings.freshness import format_minutes
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


def test_data_age_is_readable_text_with_minutes_attribute():
    ent = _sensor(sensor_mod.CarDataAgeSensor)
    value = ent.native_value
    assert isinstance(value, str) and ("min" in value or " h" in value)
    assert isinstance(ent.extra_state_attributes["minutes"], int)


def test_charge_time_sensors_show_hours_and_minutes():
    specs = {s.key: s for s in sensor_mod.CAR_SENSORS}
    for key in ("full_chg_time", "limit_chg_time", "obc_6kw"):
        spec = specs[key]
        assert spec.as_duration
        ent = _value_sensor(spec, 292)
        assert ent.native_value == "4 h 52 min"
        assert ent.extra_state_attributes == {"minutes": 292}
        assert getattr(ent, "_attr_native_unit_of_measurement", None) is None
        assert getattr(ent, "_attr_device_class", None) is None


def _value_sensor(spec, minutes):
    from dataclasses import replace

    spec = replace(spec, value=lambda car: minutes)
    coord = SimpleNamespace(data=[car_data(make_car())], _listeners=[])
    return sensor_mod.CarValueSensor(coord, "e1", "VIN1", spec, seed_car=coord.data[0])


def test_unknown_charge_time_is_unknown_not_an_error():
    spec = next(s for s in sensor_mod.CAR_SENSORS if s.key == "full_chg_time")
    assert _value_sensor(spec, 2047).native_value is None
    assert _value_sensor(spec, None).native_value is None


def test_tracker_has_a_car_icon():
    from custom_components.ha_opencarwings.device_tracker import CarTracker

    assert CarTracker._attr_icon == "mdi:car"


def test_format_minutes():
    assert format_minutes(0) == "0 min"
    assert format_minutes(37) == "37 min"
    assert format_minutes(60) == "1 h"
    assert format_minutes(150) == "2 h 30 min"
    assert format_minutes(1440 + 190) == "1 d 3 h 10 min"
    assert format_minutes(None) is None
    assert format_minutes("x") is None
    assert format_minutes(-5) is None
