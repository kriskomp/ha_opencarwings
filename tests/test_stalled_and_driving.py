from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import charging_refresh as cr
from custom_components.ha_opencarwings.freshness import (
    command_blocks,
    command_stalled,
    driving_check_due,
    driving_unconfirmed,
    idle_refresh_due,
    is_driving,
    refresh_due,
)
from tests.helpers import NOW, car_data, make_car


def _pending(seconds, command_type=1, **kw):
    return make_car(command_requested=True, command_type=command_type, command_result=-1,
                    command_request_time=NOW - timedelta(seconds=seconds), **kw)


def _driving(minutes_old, **kw):
    car = make_car(charging=False, last_updated=NOW - timedelta(minutes=minutes_old), **kw)
    car.ev_info.car_running = True
    return car


# -- unanswered refresh -----------------------------------------------------------------------------------------

def test_a_refresh_is_stalled_after_two_minutes():
    assert command_stalled(_pending(119), NOW) is False
    assert command_stalled(_pending(120), NOW) is True
    assert command_blocks(_pending(60), NOW) is True
    assert command_blocks(_pending(300), NOW) is False


def test_other_commands_are_never_stalled():
    # an A/C command must not be replaced on the server by a refresh
    assert command_stalled(_pending(600, command_type=3), NOW) is False
    assert command_blocks(_pending(600, command_type=3), NOW) is True


def test_a_finished_command_is_not_stalled():
    assert command_stalled(make_car(command_type=1, command_request_time=NOW - timedelta(hours=1)), NOW) is False


def test_charging_refresh_goes_ahead_when_the_last_refresh_got_no_answer():
    car = _pending(300, last_updated=NOW - timedelta(minutes=40))
    assert refresh_due(car, last_sent=None, interval_minutes=10, now=NOW) is True
    car = _pending(60, last_updated=NOW - timedelta(minutes=40))
    assert refresh_due(car, last_sent=None, interval_minutes=10, now=NOW) is False


class Api:
    """Records the commands and answers the polls from a script."""

    def __init__(self, reads):
        self.reads, self.sent = list(reads), []

    def __call__(self, client):
        return self

    async def api_command_create(self, vin, request):
        self.sent.append(request.command_type)
        return SimpleNamespace(car=make_car(command_requested=True, command_type=1, command_result=-1))

    async def api_car_read(self, vin):
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]


class Coordinator:
    def __init__(self, cars):
        self.data = cars
        self.push_connected = False
        self._listeners = []


async def _no_sleep(_):
    return None


@pytest.mark.asyncio
async def test_follow_refresh_asks_once_more_after_two_minutes(monkeypatch):
    waiting = make_car(command_requested=True, command_type=1, command_result=-1)
    done = make_car(command_requested=False, command_type=1, command_result=0)
    api = Api([waiting] * 8 + [done])  # 8 polls of 15 s = 120 s without an answer, then it answers
    monkeypatch.setattr(cr.opencarwings_client, "CarsApi", api)
    monkeypatch.setattr(cr.asyncio, "sleep", _no_sleep)

    result = await cr.follow_refresh(object(), Coordinator([car_data(make_car())]), "VIN1")

    assert api.sent == [1]  # exactly one repeat
    assert result is done


@pytest.mark.asyncio
async def test_follow_refresh_does_not_repeat_when_the_car_answered(monkeypatch):
    done = make_car(command_requested=False, command_type=1, command_result=0)
    api = Api([done])
    monkeypatch.setattr(cr.opencarwings_client, "CarsApi", api)
    monkeypatch.setattr(cr.asyncio, "sleep", _no_sleep)
    await cr.follow_refresh(object(), Coordinator([car_data(make_car())]), "VIN1")
    assert api.sent == []


@pytest.mark.asyncio
async def test_follow_refresh_gives_up_after_the_second_try(monkeypatch):
    waiting = make_car(command_requested=True, command_type=1, command_result=-1)
    api = Api([waiting])
    monkeypatch.setattr(cr.opencarwings_client, "CarsApi", api)
    monkeypatch.setattr(cr.asyncio, "sleep", _no_sleep)
    result = await cr.follow_refresh(object(), Coordinator([car_data(make_car())]), "VIN1")
    assert api.sent == [1] and result is waiting


# -- driving that nobody confirms ---------------------------------------------------------------------------------

def test_driving_is_unconfirmed_when_the_data_is_old():
    assert driving_unconfirmed(_driving(10), NOW) is False
    assert driving_unconfirmed(_driving(21), NOW) is True
    assert is_driving(_driving(21), NOW) is False
    assert is_driving(_driving(5), NOW) is True


def test_a_parked_car_is_never_unconfirmed_driving():
    assert driving_unconfirmed(make_car(charging=False), NOW) is False


def test_idle_check_is_no_longer_blocked_by_a_stale_driving_flag():
    old = _driving(60 * 24 * 2)
    assert idle_refresh_due(old, interval_minutes=1440, now=NOW) is True
    fresh = _driving(3)
    assert idle_refresh_due(fresh, interval_minutes=1440, now=NOW) is False


def test_driving_check_due_rules():
    car = _driving(30)
    assert driving_check_due(car, last_sent=None, interval_minutes=5, now=NOW) is True
    assert driving_check_due(car, last_sent=None, interval_minutes=0, now=NOW) is False
    assert driving_check_due(car, last_sent=NOW - timedelta(minutes=2), interval_minutes=5, now=NOW) is False
    assert driving_check_due(_driving(1), last_sent=None, interval_minutes=5, now=NOW) is False  # data is fresh
    assert driving_check_due(make_car(charging=False), last_sent=None, interval_minutes=5, now=NOW) is False
    assert driving_check_due(_pending(30, last_updated=NOW - timedelta(minutes=40)), last_sent=None,
                             interval_minutes=5, now=NOW) is False


class Hass:
    def __init__(self, coordinator):
        self.data = {DOMAIN: {"e1": {"coordinator": coordinator, "client": object()}}}
        self.tasks = []

    def async_create_task(self, coro):
        self.tasks.append(coro)
        coro.close()
        return object()


@pytest.mark.asyncio
async def test_driving_check_pauses_after_three_unanswered_questions_and_resumes_on_new_data(monkeypatch):
    car = _driving(30)
    coord = Coordinator([car_data(car)])
    coord.push_connected = True
    hass = Hass(coord)
    runner = cr.DrivingCheck(hass, "e1", 5)
    silent = make_car(command_requested=False, command_type=1, command_result=2)

    async def fake_send(entry_data, vin):
        return silent

    monkeypatch.setattr(cr, "send_refresh", fake_send)
    for _ in range(3):
        await runner._async_cycle("VIN1", NOW)
    assert "VIN1" in runner._paused_at

    await runner.async_tick(NOW + timedelta(minutes=30))
    assert hass.tasks == []  # silent car: no more questions

    car.ev_info.last_updated = runner._paused_at["VIN1"] + timedelta(minutes=1)  # it sent something itself
    car.ev_info.last_updated = NOW - timedelta(minutes=30)
    await runner.async_tick(NOW + timedelta(minutes=30))
    assert hass.tasks == []  # that data is older than the pause: still silent


@pytest.mark.asyncio
async def test_driving_check_starts_a_cycle_and_forgets_cars_that_stopped():
    car = _driving(30)
    coord = Coordinator([car_data(car)])
    coord.push_connected = True
    hass = Hass(coord)
    runner = cr.DrivingCheck(hass, "e1", 5)
    await runner.async_tick(NOW)
    assert len(hass.tasks) == 1

    runner._running.clear()
    runner._misses["VIN1"] = 2
    car.ev_info.car_running = False  # the car answered: parked
    await runner.async_tick(NOW + timedelta(minutes=10))
    assert "VIN1" not in runner._misses and len(hass.tasks) == 1
