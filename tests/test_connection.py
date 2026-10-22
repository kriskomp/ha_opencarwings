"""Live connection: reconnect, the repair issue after a long outage, one connection entity per account."""
import asyncio
from types import SimpleNamespace

import pytest

import custom_components.ha_opencarwings.binary_sensor as binary_mod
import custom_components.ha_opencarwings.button as button_mod
from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import websocket as ws_mod
from custom_components.ha_opencarwings.connection import ConnectionWatch, issue_id
from homeassistant.helpers import issue_registry as ir_stub
from tests.helpers import car_data, make_car


class Hass:
    def __init__(self):
        self.tasks = []
        self.data = {DOMAIN: {}}

    def async_create_task(self, coro):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task


async def _drain(hass):
    await asyncio.gather(*hass.tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_issue_appears_only_after_the_grace_period_and_goes_when_connected():
    ir_stub.reset()
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=False)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=0)
    watch.on_state(False)
    await _drain(hass)
    assert (DOMAIN, issue_id("e1")) in ir_stub.ISSUES
    assert ir_stub.ISSUES[(DOMAIN, issue_id("e1"))].is_fixable is True

    ws.connected = True
    watch.on_state(True)
    assert ir_stub.ISSUES == {}


@pytest.mark.asyncio
async def test_a_short_drop_raises_nothing():
    ir_stub.reset()
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=False)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=3600)
    watch.on_state(False)
    await asyncio.sleep(0)
    ws.connected = True
    watch.on_state(True)
    await _drain(hass)
    assert ir_stub.ISSUES == {}


@pytest.mark.asyncio
async def test_a_rejected_token_is_not_reported_as_a_lost_connection():
    ir_stub.reset()
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=True)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=0)
    watch.on_state(False)
    await _drain(hass)
    assert ir_stub.ISSUES == {}


@pytest.mark.asyncio
async def test_closing_the_watch_removes_the_issue():
    ir_stub.reset()
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=False)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=0)
    watch.on_state(False)
    await _drain(hass)
    watch.close()
    assert ir_stub.ISSUES == {}


@pytest.mark.asyncio
async def test_reconnect_restarts_the_loop_and_forgets_failures(monkeypatch):
    starts = []
    ws = ws_mod.OcwWebSocket(object(), "https://h", "t", on_car=lambda c: None, on_resync=lambda: None)

    async def fake_run():
        starts.append("run")
        await asyncio.Event().wait()

    monkeypatch.setattr(ws, "_run", fake_run)
    ws.start()
    await asyncio.sleep(0)
    ws._auth_failures, ws.auth_failed, ws.last_error = 5, True, "handshake 401"
    await ws.async_reconnect()
    await asyncio.sleep(0)
    assert starts == ["run", "run"]
    assert (ws._auth_failures, ws.auth_failed, ws.last_error) == (0, False, None)
    await ws.stop()


@pytest.mark.asyncio
async def test_there_is_one_reconnect_button_and_one_push_sensor_per_account():
    cars = [car_data(make_car(vin="V1", nickname="Leaf")), car_data(make_car(vin="V2", nickname="Zoe"))]
    ws = SimpleNamespace(connected=True, auth_failed=False, last_error=None, last_message_at=None, reconnects=0)

    async def reconnect():
        ws.reconnects += 1

    ws.async_reconnect = reconnect
    coordinator = SimpleNamespace(data=cars)
    hass = SimpleNamespace(data={DOMAIN: {"e1": {"coordinator": coordinator, "cars": cars, "websocket": ws}}})
    entry = SimpleNamespace(entry_id="e1", options={}, data={})

    added = []
    await button_mod.async_setup_entry(hass, entry, added.extend)
    reconnect_buttons = [e for e in added if isinstance(e, button_mod.OpenCarWingsReconnectButton)]
    assert len(reconnect_buttons) == 1
    button = reconnect_buttons[0]
    assert button.unique_id == "ha_opencarwings_reconnect_e1"
    assert button._attr_entity_category == button_mod.EntityCategory.DIAGNOSTIC
    assert button.device_info["identifiers"] == {(DOMAIN, "V1")}  # on the first car's device
    await button.async_press()
    assert ws.reconnects == 1

    sensors = []
    await binary_mod.async_setup_entry(hass, entry, sensors.extend)
    push = [e for e in sensors if isinstance(e, binary_mod.PushConnectionBinarySensor)]
    assert [e.unique_id for e in push] == ["ha_opencarwings_push_V1"]


@pytest.mark.asyncio
async def test_no_websocket_means_no_reconnect_button():
    cars = [car_data(make_car())]
    hass = SimpleNamespace(data={DOMAIN: {"e1": {"coordinator": SimpleNamespace(data=cars), "cars": cars}}})
    added = []
    await button_mod.async_setup_entry(hass, SimpleNamespace(entry_id="e1"), added.extend)
    assert not [e for e in added if isinstance(e, button_mod.OpenCarWingsReconnectButton)]
    assert not [e for e in added if getattr(e, "unique_id", "").startswith("ha_opencarwings_refresh_")]


@pytest.mark.asyncio
async def test_a_closed_watch_ignores_a_late_disconnect_report():
    # Home Assistant unloads LIFO: the socket reports "disconnected" while stopping, after watch.close().
    ir_stub.reset()
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=False)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=0)
    watch.on_state(True)
    watch.close()
    watch.on_state(False)  # the late report from the dying socket
    await _drain(hass)
    assert hass.tasks == []  # no timer was started
    assert ir_stub.ISSUES == {}


@pytest.mark.asyncio
async def test_a_timer_that_is_already_running_does_not_raise_after_close():
    ir_stub.reset()
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=False)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=0.05)
    watch.on_state(False)
    watch._closed = True  # closed without going through close(): the timer itself must still check
    await _drain(hass)
    assert ir_stub.ISSUES == {}


@pytest.mark.asyncio
async def test_a_new_watch_does_not_inherit_the_issue_of_an_old_one():
    ir_stub.reset()
    ir_stub.async_create_issue(object(), DOMAIN, issue_id("e1"), is_fixable=True, severity="warning",
                               translation_key="push_disconnected", data={"entry_id": "e1"})
    assert ir_stub.ISSUES
    hass, ws = Hass(), SimpleNamespace(connected=False, auth_failed=False)
    watch = ConnectionWatch(hass, "e1", ws, grace_seconds=3600)
    watch.start()  # a fresh setup: the leftover issue is dropped, the grace period begins
    assert ir_stub.ISSUES == {}
    watch.close()
    await _drain(hass)
