"""Minimal stand-ins for the number platform."""
from types import SimpleNamespace


class NumberDeviceClass:
    TEMPERATURE = "temperature"


class NumberMode:
    SLIDER = "slider"


class NumberEntity:
    pass


class RestoreNumber(NumberEntity):
    last = None

    async def async_added_to_hass(self):
        return None

    async def async_get_last_number_data(self):
        return type(self).last

    def async_write_ha_state(self):
        pass
