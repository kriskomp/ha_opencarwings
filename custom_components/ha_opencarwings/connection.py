"""Tell the user when the live connection stays down, and let them reconnect.

A short drop is normal (the socket reconnects by itself within seconds). When it stays down for
``DISCONNECT_GRACE_SECONDS`` a repair issue appears (Settings -> System -> Repairs) with a "Reconnect" fix;
it disappears as soon as the connection is back. A rejected token is not reported here: that already starts
the re-authentication flow.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

DISCONNECT_GRACE_SECONDS = 10 * 60
ISSUE_TRANSLATION_KEY = "push_disconnected"


def issue_id(entry_id: str) -> str:
    return f"push_disconnected_{entry_id}"


class ConnectionWatch:
    """Raises the repair issue when the connection has been down for the grace period."""

    def __init__(self, hass: Any, entry_id: str, ws: Any, *, grace_seconds: int = DISCONNECT_GRACE_SECONDS) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._ws = ws
        self._grace = grace_seconds
        self._task: Any = None

    def on_state(self, connected: bool) -> None:
        if connected:
            self._cancel()
            self._delete_issue()
        elif self._task is None:
            self._task = self._hass.async_create_task(self._raise_later())

    def close(self) -> None:
        """Entry unloaded: no timer, no leftover issue."""
        self._cancel()
        self._delete_issue()

    def _cancel(self) -> None:
        task, self._task = self._task, None
        if task is not None and hasattr(task, "cancel"):
            task.cancel()

    async def _raise_later(self) -> None:
        try:
            await asyncio.sleep(self._grace)
        except asyncio.CancelledError:
            raise
        if self._ws.connected or self._ws.auth_failed:
            return
        self._create_issue()

    def _create_issue(self) -> None:
        try:
            from homeassistant.helpers import issue_registry as ir

            ir.async_create_issue(
                self._hass,
                DOMAIN,
                issue_id(self._entry_id),
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_TRANSLATION_KEY,
                data={"entry_id": self._entry_id},
            )
        except Exception:  # noqa: BLE001 - a courtesy, never break the connection loop
            _LOGGER.debug("Could not create the repair issue", exc_info=True)

    def _delete_issue(self) -> None:
        try:
            from homeassistant.helpers import issue_registry as ir

            ir.async_delete_issue(self._hass, DOMAIN, issue_id(self._entry_id))
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not delete the repair issue", exc_info=True)
