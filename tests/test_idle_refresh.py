from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import charging_refresh as cr
from custom_components.ha_opencarwings.freshness import idle_refresh_due, last_contact
from tests.helpers import NOW, car_data, make_car

DAY = 1440


def _car(**kw):
    kw.setdefault("charging", False)
    return make_car(**kw)


def test_due_when_the_car_was_silent_for_the_whole_interval():
    car = _car(last_updated=NOW - timedelta(days=2))
    assert idle_refresh_due(car, interval_minutes=DAY, now=NOW) is True


def test_not_due_when_the_data_is_younger_than_the_interval():
    car = _car(last_updated=NOW - timedelta(hours=5))
    assert idle_refresh_due(car, interval_minutes=DAY, now=NOW) is False


def test_last_connection_counts_as_a_sign_of_life():
    car = _car(last_updated=NOW - timedelta(days=3), last_connection=NOW - timedelta(hours=2))
    assert last_contact(car) == NOW - timedelta(hours=2)
    assert idle_refresh_due(car, interval_minutes=DAY, now=NOW) is False


def test_off_means_never():
    assert idle_refresh_due(_car(last_updated=NOW - timedelta(days=30)), interval_minutes=0, now=NOW) is False


def test_never_while_charging_driving_or_pending():
    old = NOW - timedelta(days=5)
    assert idle_refresh_due(make_car(charging=True, last_updated=old), interval_minutes=DAY, now=NOW) is False
    # driving the car has not confirmed for a long time does not block the check (see test_stalled_and_driving)
    running = _car(last_updated=NOW - timedelta(minutes=2), last_connection=NOW - timedelta(minutes=2))
    running.ev_info.car_running = True
    assert idle_refresh_due(running, interval_minutes=DAY, now=NOW) is False
    assert idle_refresh_due(_car(last_updated=old, command_requested=True), interval_minutes=DAY, now=NOW) is False


def test_a_recent_command_blocks_a_retry_even_after_a_timeout():
    # protects the 12 V battery: a sleeping car that timed out is not woken again until a full interval passed
    car = _car(last_updated=NOW - timedelta(days=5), command_result=2, command_request_time=NOW - timedelta(hours=3))
    assert idle_refresh_due(car, interval_minutes=DAY, now=NOW) is False
    car = _car(last_updated=NOW - timedelta(days=5), command_result=2, command_request_time=NOW - timedelta(hours=25))
    assert idle_refresh_due(car, interval_minutes=DAY, now=NOW) is True


def test_unknown_car_state_is_handled():
    assert idle_refresh_due(None, interval_minutes=DAY, now=NOW) is False


class Coordinator:
    def __init__(self, cars, push):
        self.data, self.push_connected, self.refreshed = cars, push, 0

    async def async_request_refresh(self):
        self.refreshed += 1


class Hass:
    def __init__(self, coordinator):
        self.data = {DOMAIN: {"e1": {"coordinator": coordinator, "client": object()}}}
        self.tasks = []

    def async_create_task(self, coro):
        self.tasks.append(coro)
        coro.close()
        return object()


@pytest.mark.asyncio
async def test_tick_starts_one_cycle_for_a_silent_parked_car_and_skips_rest_when_push_is_up():
    coord = Coordinator([car_data(_car(last_updated=NOW - timedelta(days=2)))], push=True)
    hass = Hass(coord)
    runner = cr.IdleRefresh(hass, "e1", DAY)

    await runner.async_tick(NOW)

    assert len(hass.tasks) == 1
    assert coord.refreshed == 0  # the live socket keeps our copy current


@pytest.mark.asyncio
async def test_tick_reads_the_server_first_without_the_socket():
    coord = Coordinator([car_data(_car(last_updated=NOW - timedelta(hours=1)))], push=False)
    hass = Hass(coord)
    await cr.IdleRefresh(hass, "e1", DAY).async_tick(NOW)
    assert coord.refreshed == 1 and hass.tasks == []
