"""A/C: the switch keeps the chosen position until the car reports; temperature goes with the start command."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import custom_components.ha_opencarwings.switch as switch_mod
import custom_components.ha_opencarwings.number as number_mod
from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import ac as ac_mod
from custom_components.ha_opencarwings import charging_refresh as cr
from custom_components.ha_opencarwings.ac import AcController, clamp_temperature, start_payload
from homeassistant.components.number import RestoreNumber
from tests.helpers import NOW, car_data, make_car

FICOSA = [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]


def _car(*, ac_status=False, tcu_type="ficosa2016", **kwargs):
    car = make_car(**kwargs)
    car.ev_info.ac_status = ac_status
    car.tcu_type = tcu_type
    car.supported_commands = FICOSA
    return car


class FakeHass:
    def __init__(self, coordinator, controller=None, client=None):
        self.tasks = []
        self.data = {DOMAIN: {"e1": {"coordinator": coordinator, "client": client or object(), "ac": controller}}}

    def async_create_task(self, coro):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task


def _setup(car=None, hold=900):
    car = car or _car()
    coordinator = SimpleNamespace(data=[car_data(car)], _listeners=[], updates=0)

    def update():
        coordinator.updates += 1

    coordinator.async_update_listeners = update
    hass = FakeHass(coordinator)
    controller = AcController(hass, "e1", hold_seconds=hold)
    hass.data[DOMAIN]["e1"]["ac"] = controller
    return hass, coordinator, controller


def _switch(hass, coordinator):
    sw = switch_mod.CarACSwitch("e1", coordinator.data[0], coordinator)
    sw.hass = hass
    return sw


# -- temperature --------------------------------------------------------------

def test_temperature_is_whole_celsius_inside_the_servers_range():
    assert clamp_temperature(21) == 21
    assert clamp_temperature(21.4) == 21
    assert clamp_temperature(21.6) == 22
    assert clamp_temperature(10) == 16
    assert clamp_temperature(99) == 31       # the server rejects anything above 31
    assert clamp_temperature(21.11) == 21    # 70 degF arrives as 21.11 degC
    assert clamp_temperature("x") == 21
    assert clamp_temperature(None) == 21


def test_start_payload_is_celsius_and_only_for_tcus_that_take_it():
    assert start_payload(_car(), 24) == {"unit": 0, "temp": 24}
    assert start_payload(_car(tcu_type="continental2012"), 24) is None
    assert start_payload(_car(tcu_type=SimpleNamespace(value="ficosa2016")), 24) == {"unit": 0, "temp": 24}
    assert start_payload(None, 24) is None


# -- what the switch shows ------------------------------------------------------

@pytest.mark.asyncio
async def test_switch_follows_the_car_when_nothing_was_asked():
    hass, coordinator, _ = _setup(_car(ac_status=True))
    sw = _switch(hass, coordinator)
    assert sw.is_on is True
    coordinator.data = [car_data(_car(ac_status=False))]
    assert sw.is_on is False
    assert sw.icon == "mdi:fan-off"


@pytest.mark.asyncio
async def test_switch_keeps_the_chosen_position_while_the_car_still_reports_the_old_one():
    hass, coordinator, controller = _setup(_car(ac_status=False))
    sw = _switch(hass, coordinator)
    controller.request("VIN1", True, check=False)
    assert sw.is_on is True and sw.icon == "mdi:fan"
    assert coordinator.updates == 1  # listeners told, so the UI redraws at once


@pytest.mark.asyncio
async def test_the_hold_ends_after_the_hold_time():
    hass, coordinator, controller = _setup()
    controller.request("VIN1", True, check=False, now=NOW)
    assert controller.desired("VIN1", now=NOW + timedelta(minutes=14)) is True
    assert controller.desired("VIN1", now=NOW + timedelta(minutes=15)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, expected", [(4, True), (5, False), (7, False)])
async def test_the_servers_ac_alerts_settle_the_switch(kind, expected):
    hass, coordinator, controller = _setup(_car(ac_status=not expected))
    sw = _switch(hass, coordinator)
    controller.handle_alert({"type": kind, "car": {"vin": "VIN1"}})
    assert sw.is_on is expected


@pytest.mark.asyncio
async def test_an_ac_error_alert_returns_the_switch_to_the_car_state(monkeypatch):
    hass, coordinator, controller = _setup(_car(ac_status=False))
    sw = _switch(hass, coordinator)
    controller.request("VIN1", True, check=False)
    controller.handle_alert({"type": 97, "car": {"vin": "VIN1"}, "additional_data": "low charge"})
    assert sw.is_on is False


@pytest.mark.asyncio
async def test_alerts_for_other_cars_or_other_kinds_change_nothing():
    hass, coordinator, controller = _setup()
    controller.handle_alert({"type": 4, "car": {"vin": "OTHER"}})
    controller.handle_alert({"type": 1, "car": {"vin": "VIN1"}})   # charge stop
    controller.handle_alert({"type": 4})                            # no car
    controller.handle_alert("garbage")
    assert controller.desired("VIN1") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [1, 2])
async def test_a_failed_command_returns_the_switch_to_the_car_state(result):
    hass, coordinator, controller = _setup()
    controller.request("VIN1", True, check=False)
    failed = _car(command_type=3, command_result=result)
    controller.command_finished("VIN1", 3, failed)
    assert controller.desired("VIN1") is None


@pytest.mark.asyncio
async def test_a_successful_command_keeps_the_position():
    hass, coordinator, controller = _setup()
    controller.request("VIN1", True, check=False)
    controller.command_finished("VIN1", 3, _car(command_type=3, command_result=0))
    assert controller.desired("VIN1") is True


@pytest.mark.asyncio
async def test_a_failed_other_command_does_not_touch_the_switch():
    hass, coordinator, controller = _setup()
    controller.request("VIN1", True, check=False)
    controller.command_finished("VIN1", 3, _car(command_type=1, command_result=2))  # a refresh timed out
    assert controller.desired("VIN1") is True


# -- the single look at the car after the hold -------------------------------

@pytest.mark.asyncio
async def test_the_car_is_asked_once_when_it_stayed_silent(monkeypatch):
    sent = []

    async def fake_send(entry_data, vin):
        sent.append(vin)

    monkeypatch.setattr(cr, "send_refresh", fake_send)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    hass, coordinator, controller = _setup(_car(last_updated=old), hold=0)
    controller.request("VIN1", True)
    await asyncio.gather(*hass.tasks)
    assert sent == ["VIN1"]
    assert controller.desired("VIN1") is None  # the switch follows the car again


@pytest.mark.asyncio
async def test_the_car_is_not_asked_when_it_reported_in_the_meantime(monkeypatch):
    sent = []

    async def fake_send(entry_data, vin):
        sent.append(vin)

    monkeypatch.setattr(cr, "send_refresh", fake_send)
    hass, coordinator, controller = _setup(_car(last_updated=datetime.now(timezone.utc) + timedelta(minutes=1)), hold=0)
    controller.request("VIN1", True)
    await asyncio.gather(*hass.tasks)
    assert sent == []


@pytest.mark.asyncio
async def test_an_alert_cancels_the_check(monkeypatch):
    sent = []

    async def fake_send(entry_data, vin):
        sent.append(vin)

    monkeypatch.setattr(cr, "send_refresh", fake_send)
    hass, coordinator, controller = _setup(_car(last_updated=NOW - timedelta(hours=5)), hold=3600)
    controller.request("VIN1", True)
    controller.handle_alert({"type": 4, "car": {"vin": "VIN1"}})
    await asyncio.sleep(0)
    assert sent == []
    controller.cancel_all()


# -- sending commands ------------------------------------------------------------

class FakeCarsApi:
    sent = []
    fail = False

    def __init__(self, client):
        pass

    async def api_command_create(self, vin, request):
        if FakeCarsApi.fail:
            raise RuntimeError("down")
        FakeCarsApi.sent.append((vin, request.command_type, request.command_payload))
        return SimpleNamespace(car=_car())


class FakeRequest:
    def __init__(self, command_type, command_payload=None, command_pin=None):
        self.command_type, self.command_payload, self.command_pin = command_type, command_payload, command_pin


def _patch_api(monkeypatch):
    FakeCarsApi.sent, FakeCarsApi.fail = [], False
    monkeypatch.setattr(switch_mod.opencarwings_client, "CarsApi", FakeCarsApi)
    monkeypatch.setattr(switch_mod, "ApiCommandCreateRequest", FakeRequest)

    async def no_follow(client, coordinator, vin, **kwargs):
        return _car(command_type=3, command_result=0)

    monkeypatch.setattr(switch_mod, "follow_command", no_follow)


@pytest.mark.asyncio
async def test_turning_on_sends_command_3_with_the_chosen_temperature(monkeypatch):
    _patch_api(monkeypatch)
    hass, coordinator, controller = _setup()
    controller.set_temperature("VIN1", 24)
    sw = _switch(hass, coordinator)
    await sw.async_turn_on()
    assert FakeCarsApi.sent == [("VIN1", 3, {"unit": 0, "temp": 24})]
    assert sw.is_on is True   # the position stays even though the car has not reported yet
    controller.cancel_all()


@pytest.mark.asyncio
async def test_turning_on_without_a_temperature_for_other_tcus(monkeypatch):
    _patch_api(monkeypatch)
    hass, coordinator, controller = _setup(_car(tcu_type="continental2012"))
    await _switch(hass, coordinator).async_turn_on()
    assert FakeCarsApi.sent == [("VIN1", 3, None)]
    controller.cancel_all()


@pytest.mark.asyncio
async def test_turning_off_sends_command_4(monkeypatch):
    _patch_api(monkeypatch)
    hass, coordinator, controller = _setup(_car(ac_status=True))
    sw = _switch(hass, coordinator)
    await sw.async_turn_off()
    assert FakeCarsApi.sent == [("VIN1", 4, None)]
    assert sw.is_on is False
    controller.cancel_all()


@pytest.mark.asyncio
async def test_a_failed_request_puts_the_switch_back(monkeypatch):
    _patch_api(monkeypatch)
    FakeCarsApi.fail = True
    hass, coordinator, controller = _setup(_car(ac_status=False))
    sw = _switch(hass, coordinator)
    with pytest.raises(RuntimeError):
        await sw.async_turn_on()
    assert sw.is_on is False


# -- the number entity -------------------------------------------------------------

def _number(hass, coordinator, controller):
    ent = number_mod.CarACTemperatureNumber("e1", coordinator.data[0], coordinator, controller)
    ent.hass = hass
    return ent


@pytest.mark.asyncio
async def test_temperature_number_stores_whole_degrees_in_the_controller():
    hass, coordinator, controller = _setup()
    ent = _number(hass, coordinator, controller)
    assert ent.native_value == 21
    await ent.async_set_native_value(21.11)   # 70 degF
    assert controller.temperature("VIN1") == 21
    await ent.async_set_native_value(40)
    assert ent.native_value == 31
    assert (ent._attr_native_min_value, ent._attr_native_max_value) == (16, 31)
    assert ent._attr_native_unit_of_measurement == "°C"
    assert ent._attr_device_class == "temperature"
    assert ent._attr_entity_category == number_mod.EntityCategory.CONFIG
    assert ent.unique_id == "ha_opencarwings_ac_temperature_VIN1"


@pytest.mark.asyncio
async def test_temperature_is_restored_after_a_restart():
    hass, coordinator, controller = _setup()
    ent = _number(hass, coordinator, controller)
    RestoreNumber.last = SimpleNamespace(native_value=25.0)
    try:
        await ent.async_added_to_hass()
    finally:
        RestoreNumber.last = None
    assert controller.temperature("VIN1") == 25


@pytest.mark.asyncio
async def test_the_number_exists_only_for_tcus_that_take_a_temperature():
    from homeassistant.helpers import entity_registry as er_stub

    er_stub.reset()
    er_stub.add("number.old", "e1", unique_id="ha_opencarwings_ac_temperature_VIN1")
    other = _car(tcu_type="continental2012")
    hass, coordinator, controller = _setup(other)
    hass.data[DOMAIN]["e1"]["cars"] = coordinator.data
    added = []
    await number_mod.async_setup_entry(hass, SimpleNamespace(entry_id="e1"), added.extend)
    assert added == []
    assert er_stub.REGISTRY.removed == ["number.old"]

    hass, coordinator, controller = _setup(_car())
    hass.data[DOMAIN]["e1"]["cars"] = coordinator.data
    await number_mod.async_setup_entry(hass, SimpleNamespace(entry_id="e1"), added.extend)
    assert len(added) == 1
