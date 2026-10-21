import asyncio
import json
from types import SimpleNamespace

import aiohttp
import pytest

from custom_components.ha_opencarwings import websocket as ws_mod
from custom_components.ha_opencarwings import charging_refresh as cr
from tests.helpers import car_data, make_car

TEXT = aiohttp.WSMsgType.TEXT


def text(obj):
    return SimpleNamespace(type=TEXT, data=json.dumps(obj))


LISTEN = text({"type": "listen", "data": True})


class FakeWS:
    def __init__(self, messages):
        self._messages = list(messages)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def receive(self):
        return self._messages.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


class Failing:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc):
        return False


class Hang:
    async def __aenter__(self):
        await asyncio.Event().wait()

    async def __aexit__(self, *exc):
        return False


class Session:
    """Each ws_connect call takes the next scripted outcome; after the script it hangs."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def ws_connect(self, url, headers=None, heartbeat=None):
        self.calls.append({"url": url, "headers": headers, "heartbeat": heartbeat})
        return self.script.pop(0) if self.script else Hang()


class Recorder:
    def __init__(self):
        self.cars, self.states, self.resyncs, self.auth, self.alerts = [], [], 0, 0, []

    async def resync(self):
        self.resyncs += 1

    def make(self, session, **kw):
        return ws_mod.OcwWebSocket(
            session, "https://ocw.example", "TOKEN",
            on_car=self.cars.append, on_resync=self.resync,
            on_state=self.states.append, on_auth_failed=lambda: setattr(self, "auth", self.auth + 1),
            on_alert=self.alerts.append, **kw,
        )


async def until(cond, timeout=3):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(ws_mod, "BACKOFF_START", 0.01)
    monkeypatch.setattr(ws_mod, "BACKOFF_MAX", 0.02)
    monkeypatch.setattr(ws_mod, "AUTH_RETRY_SECONDS", 3600)
    monkeypatch.setattr(ws_mod, "LISTEN_TIMEOUT_SECONDS", 0.2)


@pytest.fixture
def fake_car(monkeypatch):
    import opencarwings_client

    class FakeCar:
        def __init__(self, vin):
            self.vin = vin

        @classmethod
        def from_dict(cls, data):
            if "broken" in data:
                raise ValueError("bad payload")
            return cls(data["vin"])

    monkeypatch.setattr(opencarwings_client, "Car", FakeCar)


def test_ws_url():
    assert ws_mod.ws_url("https://a.b") == "wss://a.b/ws/notif/"
    assert ws_mod.ws_url("http://a.b:8000/") == "ws://a.b:8000/ws/notif/"


@pytest.mark.asyncio
async def test_connect_sends_token_and_heartbeat_then_resyncs(fake_car):
    rec, session = Recorder(), Session([FakeWS([LISTEN, text({"type": "ev_info", "data": {"vin": "V1"}})])])
    ws = rec.make(session)
    ws.start()
    await until(lambda: [c.vin for c in rec.cars] == ["V1"])
    call = session.calls[0]
    assert call["url"] == "wss://ocw.example/ws/notif/"
    assert call["headers"] == {"Authorization": "Token TOKEN"}
    assert call["heartbeat"] == ws_mod.HEARTBEAT_SECONDS
    assert rec.resyncs == 1 and rec.states[0] is True
    await ws.stop()
    assert ws.connected is False


@pytest.mark.asyncio
async def test_reconnect_resyncs_again_because_events_are_not_replayed(fake_car):
    rec = Recorder()
    session = Session([FakeWS([LISTEN]), FakeWS([LISTEN])])
    ws = rec.make(session)
    ws.start()
    await until(lambda: rec.resyncs == 2)
    assert len(session.calls) >= 2
    await ws.stop()


@pytest.mark.asyncio
async def test_unparseable_event_falls_back_to_rest(fake_car):
    rec = Recorder()
    ws = rec.make(Session([FakeWS([LISTEN, text({"type": "car", "data": {"broken": 1}})])]))
    ws.start()
    await until(lambda: rec.resyncs == 2)  # connect + fallback
    assert rec.cars == []
    await ws.stop()


@pytest.mark.asyncio
async def test_alert_and_unknown_events(fake_car):
    rec = Recorder()
    ws = rec.make(Session([FakeWS([LISTEN, text({"type": "alert", "data": {"x": 1}}), text({"type": "other", "data": {}})])]))
    ws.start()
    await until(lambda: rec.alerts == [{"x": 1}])
    assert rec.cars == []
    await ws.stop()


@pytest.mark.asyncio
async def test_rejected_handshake_is_an_auth_failure_without_a_retry_loop():
    rec = Recorder()
    err = aiohttp.WSServerHandshakeError(None, (), status=403)
    session = Session([Failing(err)])
    ws = rec.make(session)
    ws.start()
    await until(lambda: rec.auth == 1)
    await asyncio.sleep(0.1)
    assert ws.auth_failed is True
    assert len(session.calls) == 1  # waiting for the slow retry, not hammering the server
    await ws.stop()


@pytest.mark.asyncio
async def test_closing_before_listen_repeatedly_means_bad_token():
    rec = Recorder()
    closed = SimpleNamespace(type=aiohttp.WSMsgType.CLOSED, data=None)
    session = Session([FakeWS([closed]) for _ in range(5)])
    ws = rec.make(session)
    ws.start()
    await until(lambda: rec.auth == 1)
    n = len(session.calls)
    await asyncio.sleep(0.1)
    assert n == ws_mod.AUTH_FAILURES_BEFORE_REAUTH and len(session.calls) == n
    await ws.stop()


@pytest.mark.asyncio
async def test_network_errors_back_off_and_recover(fake_car):
    rec = Recorder()
    session = Session([Failing(OSError("down")), Failing(OSError("down")), FakeWS([LISTEN])])
    ws = rec.make(session)
    ws.start()
    await until(lambda: rec.resyncs == 1)
    assert ws.auth_failed is False and rec.auth == 0
    await ws.stop()


class Coord:
    def __init__(self, cars, push):
        self.data, self.push_connected, self._listeners = cars, push, []


@pytest.mark.asyncio
async def test_follow_command_polls_slower_and_stops_early_when_push_delivered_the_result(monkeypatch):
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    reads = []

    class FakeCarsApi:
        def __init__(self, client):
            pass

        async def api_car_read(self, vin):
            reads.append(vin)
            return make_car(command_requested=True, command_result=-1)

    monkeypatch.setattr(cr.opencarwings_client, "CarsApi", FakeCarsApi)
    monkeypatch.setattr(cr.asyncio, "sleep", fake_sleep)
    coord = Coord([car_data(make_car(command_requested=False))], push=True)

    result = await cr.follow_command(object(), coord, "VIN1")

    assert sleeps == [15 * cr.PUSH_POLL_FACTOR]
    assert reads == [] and result.command_requested is False
