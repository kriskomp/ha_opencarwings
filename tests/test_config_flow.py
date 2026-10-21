from types import SimpleNamespace

import pytest

from custom_components.ha_opencarwings import config_flow as cfg
from custom_components.ha_opencarwings.config_flow import OpenCARWINGSConfigFlow


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        return FakeClient()


class AccountOk:
    def __init__(self, client):
        pass

    async def account_detail_list(self):
        return SimpleNamespace(username="kris")


class AccountFails:
    def __init__(self, client):
        pass

    async def account_detail_list(self):
        raise RuntimeError("boom")


def _flow():
    flow = OpenCARWINGSConfigFlow()
    flow.hass = FakeHass()
    return flow


@pytest.mark.asyncio
async def test_config_flow_success(monkeypatch):
    monkeypatch.setattr(cfg.opencarwings_client, "AccountApi", AccountOk)

    result = await _flow().async_step_user({"token": "t", "api_base_url": "https://custom.example"})

    assert result["type"] == "create_entry"
    assert result["title"] == "kris"
    assert result["data"]["api_token"] == "t"
    assert result["data"]["api_base_url"] == "https://custom.example"


@pytest.mark.asyncio
async def test_config_flow_scan_interval_selected(monkeypatch):
    monkeypatch.setattr(cfg.opencarwings_client, "AccountApi", AccountOk)

    result = await _flow().async_step_user({"token": "t", "scan_interval": 1})

    assert result["type"] == "create_entry"
    assert result["data"]["scan_interval"] == 1


@pytest.mark.asyncio
async def test_config_flow_failure_shows_form_with_error(monkeypatch):
    monkeypatch.setattr(cfg.opencarwings_client, "AccountApi", AccountFails)

    result = await _flow().async_step_user({"token": "bad"})

    assert result["type"] == "form"
    assert result["errors"]["base"] == "unknown"
