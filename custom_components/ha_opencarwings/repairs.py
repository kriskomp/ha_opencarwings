"""Repair flow: reconnect the live connection from Settings -> System -> Repairs."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow

from . import DOMAIN


class ReconnectRepairFlow(RepairsFlow):
    """One confirmation, then the connection is reopened."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_init(self, user_input=None):
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            ws = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("websocket")
            if ws is not None:
                await ws.async_reconnect()
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


async def async_create_fix_flow(hass, issue_id: str, data) -> RepairsFlow:
    return ReconnectRepairFlow(str((data or {}).get("entry_id", "")))
