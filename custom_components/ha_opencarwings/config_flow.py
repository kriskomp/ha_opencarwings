from __future__ import annotations

import logging

import opencarwings_client
from opencarwings_client import AccountDetail
from opencarwings_client.rest import ApiException
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN

from .api import get_client, DEFAULT_API_BASE

# Scan interval choices in minutes with friendly labels
SCAN_INTERVAL_CHOICES = [
    (1, "1 minute"),
    (5, "5 minutes"),
    (10, "10 minutes"),
    (15, "15 minutes (default)"),
    (30, "30 minutes"),
    (60, "1 hour"),
    (180, "3 hours"),
    (360, "6 hours"),
    (720, "12 hours"),
    (1440, "1 day"),
]
# Minutes between "Refresh data" commands while the car is charging (0 = off)
CHARGING_REFRESH_CHOICES = [
    (0, "Off"),
    (5, "5 minutes"),
    (10, "10 minutes"),
    (15, "15 minutes"),
    (30, "30 minutes"),
]
DEFAULT_CHARGING_REFRESH_MIN = 0
# Minutes between "is it still driving?" questions while the car reports driving (0 = off)
DRIVING_CHECK_CHOICES = [
    (0, "Off"),
    (5, "5 minutes"),
    (10, "10 minutes"),
    (15, "15 minutes"),
]
DEFAULT_DRIVING_CHECK_MIN = 0
# Minutes of silence after which a parked car is asked for data (0 = off)
IDLE_REFRESH_CHOICES = [
    (0, "Off"),
    (360, "6 hours"),
    (720, "12 hours"),
    (1440, "1 day"),
    (2880, "2 days"),
    (4320, "3 days"),
    (10080, "1 week"),
    (20160, "2 weeks"),
]
DEFAULT_IDLE_REFRESH_MIN = 0
DEFAULT_USE_WEBSOCKET = True
# Data older than this many minutes is reported as not fresh
DEFAULT_FRESH_MINUTES = 30
# Values used when selector is not available (fallback)
SCAN_INTERVAL_OPTIONS = [c[0] for c in SCAN_INTERVAL_CHOICES]
DEFAULT_SCAN_INTERVAL_MIN = 15

# Default API base URL
_LOGGER = logging.getLogger(__name__)


class OpenCARWINGSConfigFlow(config_entries.ConfigFlow, domain="ha_opencarwings"):
    """Config flow for OpenCARWINGS."""

    VERSION = 2

    @staticmethod
    def async_get_options_flow(config_entry):
        """Options flow (shown as "Configure" on the integration)."""
        return OptionsFlowHandler()

    async def async_step_reauth(self, entry_data):
        """The server rejected the API token: ask for a new one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN]
            base = entry.options.get("api_base_url", entry.data.get("api_base_url", DEFAULT_API_BASE))
            try:
                async with await self.hass.async_add_executor_job(get_client, self.hass, base, token) as client:
                    await opencarwings_client.AccountApi(client).account_detail_list()
            except ApiException as err:
                errors["base"] = "auth" if err.status == 401 else "unknown"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                # Options override data, so the new token must replace both.
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, "api_token": token},
                    options={**entry.options, "api_token": token},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}), errors=errors
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step where user provides credentials."""
        errors = {}
        if user_input is not None:
            # each user has its own API token
            api_token = user_input[CONF_TOKEN]
            api_base = user_input.get("api_base_url", DEFAULT_API_BASE)
            hass = getattr(self, "hass", None)
            async with await hass.async_add_executor_job(get_client, hass, api_base, api_token) as client:
                api_instance = opencarwings_client.AccountApi(client)
                try:
                    account_info: AccountDetail = await api_instance.account_detail_list()
                    return self.async_create_entry(
                        title=account_info.username,
                        data={
                            "account_info": account_info.username,
                            "api_token": api_token,
                            # persist initial scan interval choice
                            "scan_interval": user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL_MIN),
                            "api_base_url": api_base,
                        },
                    )
                except ApiException as err:
                    _LOGGER.exception(err)
                    if err.status == 401:
                        errors["base"] = "auth"
                    else:
                        errors["base"] = err.body
                except Exception as err:
                    _LOGGER.exception(err)
                    errors["base"] = "unknown"

        # Prefer to show a pretty select when Home Assistant's selector helpers
        # are available; fall back to a numeric choice list otherwise.
        try:
            from homeassistant.helpers import selector

            scan_selector = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": v, "label": l} for v, l in SCAN_INTERVAL_CHOICES]
                )
            )
        except Exception:
            # selector not available in minimal test stubs — use numeric options
            scan_selector = vol.In(SCAN_INTERVAL_OPTIONS)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL_MIN): scan_selector,
                vol.Required("api_base_url", default=DEFAULT_API_BASE): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)


def _select(choices):
    """A select selector; Home Assistant selectors need string values."""
    try:
        from homeassistant.helpers import selector

        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": str(v), "label": l} for v, l in choices]
            )
        )
    except Exception:  # selector not available in minimal test stubs
        return vol.In([str(v) for v, _ in choices])


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options: token, API address, poll interval, charging refresh, freshness."""

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        if user_input is not None:
            data = dict(user_input)
            for key in ("scan_interval", "charging_refresh_interval", "idle_refresh_interval", "driving_check_interval", "data_fresh_minutes"):
                if key in data:
                    data[key] = int(data[key])
            return self.async_create_entry(title="", data=data)

        def current(key, default):
            return entry.options.get(key, entry.data.get(key, default))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("api_token", default=current("api_token", "")): str,
                vol.Required("api_base_url", default=current("api_base_url", DEFAULT_API_BASE)): str,
                vol.Required(
                    "scan_interval", default=str(current("scan_interval", DEFAULT_SCAN_INTERVAL_MIN))
                ): _select(SCAN_INTERVAL_CHOICES),
                vol.Required(
                    "use_websocket", default=bool(current("use_websocket", DEFAULT_USE_WEBSOCKET))
                ): bool,
                vol.Required(
                    "charging_refresh_interval",
                    default=str(current("charging_refresh_interval", DEFAULT_CHARGING_REFRESH_MIN)),
                ): _select(CHARGING_REFRESH_CHOICES),
                vol.Required(
                    "idle_refresh_interval",
                    default=str(current("idle_refresh_interval", DEFAULT_IDLE_REFRESH_MIN)),
                ): _select(IDLE_REFRESH_CHOICES),
                vol.Required(
                    "driving_check_interval",
                    default=str(current("driving_check_interval", DEFAULT_DRIVING_CHECK_MIN)),
                ): _select(DRIVING_CHECK_CHOICES),
                vol.Required(
                    "data_fresh_minutes", default=int(current("data_fresh_minutes", DEFAULT_FRESH_MINUTES))
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                vol.Required("track_location", default=bool(current("track_location", True))): bool,
            }),
        )
