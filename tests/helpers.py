"""Small fakes shared by the tests."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.ha_opencarwings.util import CarData  # noqa: E402

NOW = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)


class FakeCar(SimpleNamespace):
    """A ``Car`` look-alike. ``to_dict`` drops read-only timestamps, like the real client."""

    def to_dict(self):
        return {"nickname": getattr(self, "nickname", None), "command_requested": self.command_requested}


def make_car(
    *,
    charging=True,
    charge_finish=False,
    last_updated=NOW - timedelta(minutes=20),
    last_connection=None,
    command_requested=False,
    command_type=0,
    command_result=0,
    command_request_time=None,
    nickname="Leaf",
    vin="VIN1",
):
    ev = SimpleNamespace(
        charging=charging,
        quick_charging=False,
        charge_finish=charge_finish,
        last_updated=last_updated,
    )
    return FakeCar(
        vin=vin,
        nickname=nickname,
        ev_info=ev,
        last_connection=last_connection,
        command_requested=command_requested,
        command_type=command_type,
        command_type_display="Refresh data",
        command_result=command_result,
        command_result_display={0: "Success", 1: "Error", 2: "Timeout", -1: "Waiting"}[command_result],
        command_request_time=command_request_time,
    )


def car_data(car) -> CarData:
    return CarData(vin=car.vin, car_detail=car)
