from types import SimpleNamespace

import pytest

from custom_components.ha_opencarwings.config_flow import OpenCARWINGSConfigFlow, OptionsFlowHandler


def _handler(options=None, data=None):
    handler = OptionsFlowHandler()
    handler.config_entry = SimpleNamespace(
        options=options or {}, data=data or {"api_token": "tok", "scan_interval": 15}
    )
    return handler


def test_config_flow_exposes_the_options_flow():
    assert isinstance(OpenCARWINGSConfigFlow.async_get_options_flow(SimpleNamespace()), OptionsFlowHandler)


@pytest.mark.asyncio
async def test_options_form_defaults_come_from_the_entry():
    result = await _handler().async_step_init()
    assert result["type"] == "form"
    keys = {str(k): k for k in result["data_schema"].schema}
    assert {"api_token", "api_base_url", "scan_interval", "charging_refresh_interval", "idle_refresh_interval", "driving_check_interval", "command_timeout_s", "driving_stale_min", "data_fresh_minutes", "track_location"} <= set(keys)
    assert keys["api_token"].default() == "tok"
    assert keys["charging_refresh_interval"].default() == "0"
    assert keys["idle_refresh_interval"].default() == "0"
    assert keys["driving_check_interval"].default() == "0"
    assert keys["command_timeout_s"].default() == 300
    assert keys["driving_stale_min"].default() == 20
    assert keys["data_fresh_minutes"].default() == 30
    assert keys["track_location"].default() is True


@pytest.mark.asyncio
async def test_options_are_saved_as_integers():
    result = await _handler().async_step_init({
        "api_token": "tok2",
        "api_base_url": "https://x.example",
        "scan_interval": "5",
        "charging_refresh_interval": "10",
        "data_fresh_minutes": "45",
        "track_location": False,
    })
    assert result["type"] == "create_entry"
    assert result["data"]["scan_interval"] == 5
    assert result["data"]["charging_refresh_interval"] == 10
    assert result["data"]["data_fresh_minutes"] == 45
    assert result["data"]["api_token"] == "tok2"
    assert result["data"]["track_location"] is False
