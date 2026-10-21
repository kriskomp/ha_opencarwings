"""Stub of homeassistant.helpers.event: records the registered intervals."""

CALLS = []


def async_track_time_interval(hass, action, interval):
    CALLS.append({"action": action, "interval": interval})

    def _unsub():
        CALLS.append({"unsubscribed": action})

    return _unsub
