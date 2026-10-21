import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.ha_opencarwings import DOMAIN
from custom_components.ha_opencarwings import charging_refresh as cr
from tests.helpers import NOW, car_data, make_car


class Coordinator:
    def __init__(self, cars):
        self.data = cars
        self.refreshed = 0
        self._listeners = []

    async def async_request_refresh(self):
        self.refreshed += 1


class Hass:
    def __init__(self, coordinator):
        self.data = {DOMAIN: {"e1": {"coordinator": coordinator, "client": object()}}}
        self.tasks = []

    def async_create_task(self, coro):
        self.tasks.append(coro)
        coro.close()  # the cycle itself is tested separately
        return object()


@pytest.mark.asyncio
async def test_tick_starts_a_cycle_for_a_charging_car():
    coord = Coordinator([car_data(make_car())])
    hass = Hass(coord)
    runner = cr.ChargingRefresh(hass, "e1", 10)

    await runner.async_tick(NOW)

    assert coord.refreshed == 1  # polls first, so the charging flag is current
    assert len(hass.tasks) == 1


@pytest.mark.asyncio
async def test_tick_does_nothing_for_a_car_that_is_not_charging():
    hass = Hass(Coordinator([car_data(make_car(charging=False))]))
    await cr.ChargingRefresh(hass, "e1", 10).async_tick(NOW)
    assert hass.tasks == []


@pytest.mark.asyncio
async def test_tick_does_not_repeat_within_the_interval():
    hass = Hass(Coordinator([car_data(make_car())]))
    runner = cr.ChargingRefresh(hass, "e1", 10)
    await runner.async_tick(NOW)
    runner._running.clear()
    await runner.async_tick(NOW + timedelta(minutes=3))
    assert len(hass.tasks) == 1


@pytest.mark.asyncio
async def test_tick_skips_car_whose_cycle_is_still_running():
    hass = Hass(Coordinator([car_data(make_car())]))
    runner = cr.ChargingRefresh(hass, "e1", 10)
    runner._running["VIN1"] = object()
    await runner.async_tick(NOW)
    assert hass.tasks == []


def test_store_car_replaces_detail_and_notifies():
    old, new = make_car(), make_car(last_updated=NOW)
    coord = Coordinator([car_data(old)])
    seen = []
    coord._listeners.append(lambda: seen.append(1))

    assert cr.store_car(coord, "VIN1", new) is True
    assert coord.data[0].car_detail is new
    assert seen == [1]
    assert cr.store_car(coord, "OTHER", new) is False
    assert cr.store_car(None, "VIN1", new) is False


@pytest.mark.asyncio
async def test_follow_command_polls_until_the_server_reports_a_result(monkeypatch):
    pending = make_car(command_requested=True, command_result=-1)
    done = make_car(command_type=1, command_result=0, command_request_time=NOW)
    reads = iter([pending, pending, done])

    class FakeCarsApi:
        def __init__(self, client):
            pass

        async def api_car_read(self, vin):
            return next(reads)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(cr.opencarwings_client, "CarsApi", FakeCarsApi)
    monkeypatch.setattr(cr.asyncio, "sleep", no_sleep)
    coord = Coordinator([car_data(make_car())])

    result = await cr.follow_command(object(), coord, "VIN1")

    assert result is done
    assert coord.data[0].car_detail is done


@pytest.mark.asyncio
async def test_follow_command_gives_up_after_the_timeout(monkeypatch):
    pending = make_car(command_requested=True, command_result=-1)
    calls = []

    class FakeCarsApi:
        def __init__(self, client):
            pass

        async def api_car_read(self, vin):
            calls.append(vin)
            return pending

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(cr.opencarwings_client, "CarsApi", FakeCarsApi)
    monkeypatch.setattr(cr.asyncio, "sleep", no_sleep)

    result = await cr.follow_command(object(), Coordinator([car_data(make_car())]), "VIN1",
                                     poll_seconds=15, timeout_seconds=60)

    assert result is pending
    assert len(calls) == 4
