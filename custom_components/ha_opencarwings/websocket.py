"""Live updates from OpenCARWINGS over WebSocket (``/ws/notif/``).

The server pushes the full car (same shape as ``GET /api/car/<vin>/``) whenever a
car packet, a location, a configuration or a command changes. Authentication is the
same personal API token as for REST, sent in the ``Authorization`` header.

What the WebSocket does *not* do, and how this module covers it:

* **No replay.** Events sent while we were disconnected are lost, so after every
  (re)connect the whole state is re-read over REST (``on_resync``), and the
  coordinator keeps a slow safety poll.
* **No application ping.** aiohttp ``heartbeat`` detects dead connections and the
  loop reconnects with a growing delay.
* **Auth failures.** A rejected handshake (401/403), or a socket closed before the
  server's ``listen`` message, is treated as a bad token: no fast retry loop, a slow
  retry and ``on_auth_failed`` (reauth) after a few attempts.
* **It cannot ask the car for new data.** The "Refresh data" command is still needed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import aiohttp

_LOGGER = logging.getLogger(__name__)

WS_PATH = "/ws/notif/"
HEARTBEAT_SECONDS = 30
LISTEN_TIMEOUT_SECONDS = 15
BACKOFF_START = 5
BACKOFF_MAX = 300
AUTH_RETRY_SECONDS = 3600
AUTH_FAILURES_BEFORE_REAUTH = 3
# Message types that carry a full car.
CAR_EVENTS = frozenset({"car", "ev_info", "location", "tcu_configuration", "send_to_car"})


def ws_url(base_url: str) -> str:
    """``https://host`` -> ``wss://host/ws/notif/`` (also keeps a path prefix)."""
    base = (base_url or "").rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return base + WS_PATH


class OcwWebSocket:
    """Keeps one WebSocket open and feeds events to callbacks."""

    def __init__(
        self,
        session: Any,
        base_url: str,
        token: str,
        *,
        on_car: Callable[[Any], None],
        on_resync: Callable[[], Awaitable[None]],
        on_state: Callable[[bool], None] | None = None,
        on_auth_failed: Callable[[], None] | None = None,
        on_alert: Callable[[dict], None] | None = None,
    ) -> None:
        self._session = session
        self._url = ws_url(base_url)
        self._token = token
        self._on_car = on_car
        self._on_resync = on_resync
        self._on_state = on_state
        self._on_auth_failed = on_auth_failed
        self._on_alert = on_alert
        self._task: asyncio.Task | None = None
        self.connected = False
        self.auth_failed = False
        self.last_message_at: float | None = None
        self.last_error: str | None = None
        self._auth_failures = 0
        self._stopping = False

    # -- lifecycle ---------------------------------------------------------
    def start(self, create_task: Callable[[Any], asyncio.Task] = asyncio.ensure_future) -> None:
        if self._task is None:
            self._stopping = False
            self._task = create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._set_connected(False)

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            if self._on_state is not None:
                self._on_state(value)

    # -- main loop ---------------------------------------------------------
    async def _run(self) -> None:
        delay = BACKOFF_START
        while not self._stopping:
            reached_listen = False
            try:
                reached_listen = await self._session_once()
                if reached_listen:
                    delay = BACKOFF_START
                    self._auth_failures = 0
                    self.auth_failed = False
                else:
                    self._auth_failures += 1
            except asyncio.CancelledError:
                raise
            except aiohttp.WSServerHandshakeError as err:
                self.last_error = f"handshake {err.status}"
                if err.status in (401, 403):
                    self._auth_failures += 1
                    self._note_auth_failure()
                    await asyncio.sleep(AUTH_RETRY_SECONDS)
                    continue
                _LOGGER.warning("OpenCARWINGS WebSocket handshake failed: %s", err)
            except Exception as err:  # noqa: BLE001 - network errors of any kind
                self.last_error = str(err) or type(err).__name__
                _LOGGER.debug("OpenCARWINGS WebSocket error: %s", err)
            finally:
                self._set_connected(False)

            if self._stopping:
                return
            if not reached_listen and self._auth_failures >= AUTH_FAILURES_BEFORE_REAUTH:
                # Closed before "listen" again and again: the server does that for a bad token.
                self._note_auth_failure()
                await asyncio.sleep(AUTH_RETRY_SECONDS)
                continue
            await asyncio.sleep(delay)
            delay = min(delay * 2, BACKOFF_MAX)

    def _note_auth_failure(self) -> None:
        if not self.auth_failed:
            self.auth_failed = True
            _LOGGER.error("OpenCARWINGS WebSocket rejected the API token; check the token in the integration options")
            if self._on_auth_failed is not None and self._auth_failures >= 1:
                self._on_auth_failed()

    async def _session_once(self) -> bool:
        """One connection. Returns True when the server sent ``listen``."""
        headers = {"Authorization": f"Token {self._token}"}
        async with self._session.ws_connect(self._url, headers=headers, heartbeat=HEARTBEAT_SECONDS) as ws:
            try:
                first = await asyncio.wait_for(ws.receive(), LISTEN_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                return False
            if first.type != aiohttp.WSMsgType.TEXT or not self._is_listen(first.data):
                return False
            # Connected. Anything that happened while we were away is gone: re-read it.
            self._set_connected(True)
            try:
                await self._on_resync()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Resync after WebSocket connect failed")
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                    break
            return True

    @staticmethod
    def _is_listen(raw: str) -> bool:
        try:
            msg = json.loads(raw)
        except ValueError:
            return False
        return isinstance(msg, dict) and msg.get("type") == "listen" and bool(msg.get("data"))

    def _handle(self, raw: str) -> None:
        import time

        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        self.last_message_at = time.time()
        kind = msg.get("type")
        data = msg.get("data")
        if kind in CAR_EVENTS and isinstance(data, dict):
            try:
                from opencarwings_client import Car

                car = Car.from_dict(data)
            except Exception:  # noqa: BLE001 - unexpected shape: fall back to REST
                _LOGGER.debug("Could not parse %s event, resyncing over REST", kind)
                asyncio.ensure_future(self._on_resync())
                return
            if car is not None and car.vin:
                self._on_car(car)
        elif kind == "alert" and self._on_alert is not None and isinstance(data, dict):
            self._on_alert(data)
