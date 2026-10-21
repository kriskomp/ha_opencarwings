from datetime import timedelta
from types import SimpleNamespace

import pytest

import custom_components.ha_opencarwings as init_mod
from homeassistant.helpers import event as event_stub


class Services:
    def async_register(self, *args, **kwargs):
        pass


class ConfigEntries:
    async def async_forward_entry_setups(self, *args, **kwargs):
        return None


def _entry(options):
    unloads = []
    return SimpleNamespace(
        entry_id="e1", title="t", data={"api_token": "t", "api_base_url": "https://x"}, options=options,
        async_on_unload=unloads.append, add_update_listener=lambda fn: (lambda: None), unloads=unloads,
    )


async def _setup(monkeypatch, options):
    import custom_components.ha_opencarwings.api as api_mod
    import opencarwings_client

    class FakeCarsApi:
        def __init__(self, client):
            pass

        async def api_car_list(self):
            return []

    monkeypatch.setattr(api_mod, "get_client", lambda hass, base, token: object())
    monkeypatch.setattr(opencarwings_client, "CarsApi", FakeCarsApi)

    class Hass:
        data = {}
        services = Services()
        config_entries = ConfigEntries()

        def async_create_task(self, coro):
            coro.close()

        async def async_add_executor_job(self, func, *args):
            return func(*args)

    event_stub.CALLS.clear()
    hass = Hass()
    hass.data = {}
    entry = _entry({"use_websocket": False, **options})
    assert await init_mod.async_setup_entry(hass, entry) is True
    return hass, entry


@pytest.mark.asyncio
async def test_charging_refresh_is_off_by_default(monkeypatch):
    hass, _ = await _setup(monkeypatch, {})
    assert "charging_refresh" not in hass.data[init_mod.DOMAIN]["e1"]
    assert event_stub.CALLS == []


@pytest.mark.asyncio
async def test_charging_refresh_registers_an_interval(monkeypatch):
    hass, entry = await _setup(monkeypatch, {"charging_refresh_interval": 5})
    runner = hass.data[init_mod.DOMAIN]["e1"]["charging_refresh"]
    assert runner.interval_minutes == 5
    assert event_stub.CALLS[0]["interval"] == timedelta(minutes=5)
    assert event_stub.CALLS[0]["action"] == runner.async_tick
    assert len(entry.unloads) == 2  # the interval and the options-reload listener


@pytest.mark.asyncio
async def test_scan_interval_given_as_a_string_still_works(monkeypatch):
    hass, _ = await _setup(monkeypatch, {"scan_interval": "5"})
    assert hass.data[init_mod.DOMAIN]["e1"]["coordinator"].update_interval == timedelta(minutes=5)


@pytest.mark.asyncio
async def test_websocket_slows_polling_while_connected(monkeypatch):
    import custom_components.ha_opencarwings.websocket as ws_mod
    from homeassistant.helpers import aiohttp_client

    created = []

    class FakeWS:
        connected = False

        def __init__(self, session, base_url, token, **callbacks):
            self.callbacks = callbacks
            created.append(self)

        def start(self, create_task=None):
            pass

        async def stop(self):
            pass

    monkeypatch.setattr(ws_mod, "OcwWebSocket", FakeWS)
    monkeypatch.setattr(aiohttp_client, "async_get_clientsession", lambda hass: object())
    hass, entry = await _setup(monkeypatch, {"use_websocket": True, "scan_interval": 5})
    coordinator = hass.data[init_mod.DOMAIN]["e1"]["coordinator"]
    ws = created[0]
    assert hass.data[init_mod.DOMAIN]["e1"]["websocket"] is ws

    ws.callbacks["on_state"](True)
    assert coordinator.push_connected is True
    assert coordinator.update_interval == timedelta(minutes=init_mod.SAFETY_POLL_MIN)

    ws.callbacks["on_state"](False)
    assert coordinator.push_connected is False
    assert coordinator.update_interval == timedelta(minutes=5)
