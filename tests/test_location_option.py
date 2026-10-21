from types import SimpleNamespace

import pytest

import custom_components.ha_opencarwings as init_mod
from custom_components.ha_opencarwings import device_tracker as dt
from custom_components.ha_opencarwings.options import track_location_enabled
from custom_components.ha_opencarwings.sensor import CarStatusSensor
from homeassistant.helpers import entity_registry as registry_stub
from tests.helpers import NOW, FakeLocation, car_data, make_car


def _place(lat=52.1, lon=21.0):
    return FakeLocation(lat=lat, lon=lon, last_updated=NOW)


def _entry(**options):
    return SimpleNamespace(entry_id="e1", options=options, data={})


def _hass(coordinator):
    return SimpleNamespace(data={init_mod.DOMAIN: {"e1": {"coordinator": coordinator, "cars": coordinator.data}}})


def test_option_defaults_to_on_and_reads_options_before_data():
    assert track_location_enabled(SimpleNamespace(options={}, data={})) is True
    assert track_location_enabled(SimpleNamespace(options={"track_location": False}, data={"track_location": True})) is False
    assert track_location_enabled(SimpleNamespace(options={}, data={"track_location": False})) is False


@pytest.mark.asyncio
async def test_no_tracker_is_created_when_the_option_is_off():
    registry_stub.reset()
    registry_stub.add("device_tracker.leaf_tracker", "e1")
    registry_stub.add("sensor.leaf_status", "e1")
    registry_stub.add("device_tracker.other_entry", "e2")
    added = []
    coordinator = SimpleNamespace(data=[car_data(make_car(location=_place()))])

    await dt.async_setup_entry(_hass(coordinator), _entry(track_location=False), added.extend)

    assert added == []
    # only this entry's tracker goes; other platforms and other entries stay
    assert registry_stub.REGISTRY.removed == ["device_tracker.leaf_tracker"]


@pytest.mark.asyncio
async def test_tracker_is_created_when_the_option_is_on():
    registry_stub.reset()
    added = []
    coordinator = SimpleNamespace(data=[car_data(make_car(location=_place()))])

    await dt.async_setup_entry(_hass(coordinator), _entry(track_location=True), added.extend)

    assert len(added) == 1
    assert added[0].unique_id == "ha_opencarwings_tracker_VIN1"
    assert registry_stub.REGISTRY.removed == []


def test_tracker_follows_the_coordinator_data():
    coordinator = SimpleNamespace(data=[car_data(make_car(location=_place(52.1, 21.0)))])
    tracker = dt.CarTracker("e1", coordinator.data[0], coordinator)
    assert (tracker.latitude, tracker.longitude) == (52.1, 21.0)

    # a refresh replaces the CarData objects; the tracker must not keep the old one
    coordinator.data = [car_data(make_car(location=_place(50.0, 19.9)))]
    assert (tracker.latitude, tracker.longitude) == (50.0, 19.9)


def test_tracker_unavailable_without_a_position_and_no_crash_on_attributes():
    car = make_car(location=None)
    coordinator = SimpleNamespace(data=[car_data(car)])
    tracker = dt.CarTracker("e1", coordinator.data[0], coordinator)
    assert tracker.available is False
    assert tracker.extra_state_attributes == {}


def test_tracker_attributes_include_the_last_update_time():
    car = make_car(location=_place())
    coordinator = SimpleNamespace(data=[car_data(car)])
    attrs = dt.CarTracker("e1", coordinator.data[0], coordinator).extra_state_attributes
    assert attrs["lat"] == 52.1
    assert attrs["last_updated"] == "21.10.2026 08:00"


def test_status_sensor_hides_the_position_in_raw_car_when_tracking_is_off():
    car = make_car(location=_place())
    coordinator = SimpleNamespace(data=[car_data(car)])

    with_location = CarStatusSensor(coordinator, "e1", "VIN1", include_location=True)
    without_location = CarStatusSensor(coordinator, "e1", "VIN1", include_location=False)

    assert "location" in with_location.extra_state_attributes["raw_car"]
    assert "location" not in without_location.extra_state_attributes["raw_car"]
    assert without_location.extra_state_attributes["raw_car"]["nickname"] == "Leaf"
