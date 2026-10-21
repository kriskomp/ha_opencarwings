from datetime import timedelta

from custom_components.ha_opencarwings import freshness as fr
from tests.helpers import NOW, make_car


def test_data_timestamp_prefers_ev_info_over_last_connection():
    car = make_car(last_updated=NOW - timedelta(minutes=5), last_connection=NOW - timedelta(hours=3))
    ts, source = fr.data_timestamp(car)
    assert ts == NOW - timedelta(minutes=5)
    assert source == "ev_info.last_updated"


def test_data_timestamp_falls_back_to_last_connection():
    car = make_car(last_updated=None, last_connection=NOW - timedelta(hours=1))
    ts, source = fr.data_timestamp(car)
    assert source == "last_connection"
    assert fr.data_age_minutes(car, NOW) == 60


def test_data_timestamp_accepts_iso_strings_and_naive_datetimes():
    assert fr.as_datetime("2026-10-21T07:00:00Z") == NOW - timedelta(hours=1)
    assert fr.as_datetime("2026-10-21T07:00:00").tzinfo is not None
    assert fr.as_datetime("garbage") is None
    assert fr.as_datetime(None) is None


def test_no_timestamp_means_unknown_age_and_not_fresh():
    car = make_car(last_updated=None, last_connection=None)
    assert fr.data_age_minutes(car, NOW) is None
    assert fr.is_fresh(None, 30) is False


def test_is_fresh_threshold():
    assert fr.is_fresh(29.9, 30) is True
    assert fr.is_fresh(30.1, 30) is False


def test_is_charging_ignores_plugged_in_only_and_finished_charge():
    assert fr.is_charging(make_car(charging=True)) is True
    assert fr.is_charging(make_car(charging=False)) is False
    assert fr.is_charging(make_car(charging=True, charge_finish=True)) is False


def test_command_summary_marks_confirmed_refresh():
    sent = NOW - timedelta(minutes=2)
    car = make_car(command_type=1, command_result=0, command_request_time=sent)
    summary = fr.command_summary(car)
    assert summary["command_result_display"] == "Success"
    assert summary["last_confirmed_refresh"] == sent


def test_command_summary_pending_is_not_confirmed():
    car = make_car(command_type=1, command_result=-1, command_requested=True, command_request_time=NOW)
    summary = fr.command_summary(car)
    assert summary["command_requested"] is True
    assert summary["last_confirmed_refresh"] is None


def test_command_summary_other_command_is_not_a_confirmed_refresh():
    car = make_car(command_type=2, command_result=0, command_request_time=NOW)
    assert fr.command_summary(car)["last_confirmed_refresh"] is None


def test_refresh_due_when_charging_and_data_old_enough():
    car = make_car(last_updated=NOW - timedelta(minutes=20))
    assert fr.refresh_due(car, last_sent=None, interval_minutes=10, now=NOW) is True


def test_refresh_not_due_when_disabled_not_charging_or_pending():
    assert fr.refresh_due(make_car(), last_sent=None, interval_minutes=0, now=NOW) is False
    assert fr.refresh_due(make_car(charging=False), last_sent=None, interval_minutes=10, now=NOW) is False
    assert fr.refresh_due(make_car(command_requested=True), last_sent=None, interval_minutes=10, now=NOW) is False


def test_refresh_not_due_right_after_a_command_or_with_young_data():
    sent = NOW - timedelta(minutes=3)
    assert fr.refresh_due(make_car(), last_sent=sent, interval_minutes=10, now=NOW) is False
    young = make_car(last_updated=NOW - timedelta(minutes=2))
    assert fr.refresh_due(young, last_sent=None, interval_minutes=10, now=NOW) is False


def test_refresh_due_when_age_unknown():
    car = make_car(last_updated=None)
    assert fr.refresh_due(car, last_sent=None, interval_minutes=10, now=NOW) is True


def test_format_local_is_short_day_first():
    assert fr.format_local(NOW) == "21.10.2026 08:00"
    assert fr.format_local(None) is None


def test_fresh_threshold_reads_options_then_data_then_default():
    from types import SimpleNamespace as NS

    assert fr.fresh_threshold(NS(options={"data_fresh_minutes": 45}, data={})) == 45
    assert fr.fresh_threshold(NS(options={}, data={"data_fresh_minutes": "20"})) == 20
    assert fr.fresh_threshold(NS(options={}, data={})) == fr.DEFAULT_FRESH_MINUTES
    assert fr.fresh_threshold(NS(options={"data_fresh_minutes": "x"}, data={})) == fr.DEFAULT_FRESH_MINUTES
