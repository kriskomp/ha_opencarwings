from datetime import timedelta
from types import SimpleNamespace

from custom_components.ha_opencarwings import freshness
from custom_components.ha_opencarwings.binary_sensor import CarDataFreshBinarySensor
from custom_components.ha_opencarwings.sensor import (
    CarCommandStatusSensor,
    CarDataAgeSensor,
    CarLastUpdatedSensor,
    CarStatusSensor,
)
from tests.helpers import NOW, car_data, make_car


def _coord(car):
    return SimpleNamespace(data=[car_data(car)])


def test_last_updated_reads_the_model_not_to_dict(monkeypatch):
    car = make_car(last_updated=NOW - timedelta(minutes=7))
    sensor = CarLastUpdatedSensor(_coord(car), "e1", "VIN1")
    assert sensor.native_value == NOW - timedelta(minutes=7)
    assert sensor.extra_state_attributes["source"] == "ev_info.last_updated"
    assert "last_updated" not in car.to_dict()  # the reason the old sensor was always "unknown"


def test_last_updated_is_none_without_any_timestamp():
    car = make_car(last_updated=None, last_connection=None)
    assert CarLastUpdatedSensor(_coord(car), "e1", "VIN1").native_value is None


def test_data_age_sensor_counts_whole_minutes(monkeypatch):
    # data_age_minutes reads the clock; pin it in the sensor module
    from custom_components.ha_opencarwings import sensor as sensor_mod

    monkeypatch.setattr(sensor_mod, "data_age_minutes", lambda car: freshness.data_age_minutes(car, NOW))
    car = make_car(last_updated=NOW - timedelta(minutes=42, seconds=30))
    assert CarDataAgeSensor(_coord(car), "e1", "VIN1").native_value == "42 min"


def test_command_status_waiting_then_result():
    waiting = make_car(command_requested=True, command_result=-1, command_type=1)
    assert CarCommandStatusSensor(_coord(waiting), "e1", "VIN1").native_value == "waiting"

    done = make_car(command_type=1, command_result=0, command_request_time=NOW)
    sensor = CarCommandStatusSensor(_coord(done), "e1", "VIN1")
    assert sensor.native_value == "success"
    assert sensor.extra_state_attributes["last_confirmed_refresh"] == "21.10.2026 08:00"

    timeout = make_car(command_result=2)
    assert CarCommandStatusSensor(_coord(timeout), "e1", "VIN1").native_value == "timeout"


def test_status_sensor_exposes_real_timestamps():
    car = make_car(last_updated=NOW - timedelta(minutes=5), last_connection=NOW - timedelta(minutes=9))
    attrs = CarStatusSensor(_coord(car), "e1", "VIN1").extra_state_attributes
    assert attrs["last_evinfo"] == "21.10.2026 07:55"
    assert attrs["last_connection"] == "21.10.2026 07:51"


def test_data_fresh_binary_sensor(monkeypatch):
    from custom_components.ha_opencarwings import binary_sensor as bs

    monkeypatch.setattr(bs, "data_age_minutes", lambda car: freshness.data_age_minutes(car, NOW))
    young = make_car(last_updated=NOW - timedelta(minutes=10))
    old = make_car(last_updated=NOW - timedelta(minutes=90))
    assert CarDataFreshBinarySensor(_coord(young), "e1", "VIN1", 30).is_on is True
    stale = CarDataFreshBinarySensor(_coord(old), "e1", "VIN1", 30)
    assert stale.is_on is False
    attrs = stale.extra_state_attributes
    assert attrs["threshold_minutes"] == 30
    assert attrs["age_minutes"] == 90
    assert attrs["source"] == "ev_info.last_updated"


def test_unique_ids_are_stable():
    car = make_car()
    assert CarDataAgeSensor(_coord(car), "e1", "VIN1").unique_id == "ha_opencarwings_data_age_VIN1"
    assert CarCommandStatusSensor(_coord(car), "e1", "VIN1").unique_id == "ha_opencarwings_command_status_VIN1"
    assert CarDataFreshBinarySensor(_coord(car), "e1", "VIN1", 30).unique_id == "ha_opencarwings_data_fresh_VIN1"
    assert CarLastUpdatedSensor(_coord(car), "e1", "VIN1").unique_id == "ha_opencarwings_last_updated_VIN1"
