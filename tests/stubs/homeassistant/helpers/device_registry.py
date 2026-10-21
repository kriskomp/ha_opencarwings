"""Stub of homeassistant.helpers.device_registry."""
from types import SimpleNamespace


class FakeDeviceRegistry:
    def __init__(self):
        self.devices = []
        self.removed = []

    def async_get_device(self, identifiers=None, connections=None):
        for d in self.devices:
            if d.identifiers & set(identifiers or ()):
                return d
        return None

    def async_remove_device(self, device_id):
        self.removed.append(device_id)
        self.devices = [d for d in self.devices if d.id != device_id]


REGISTRY = FakeDeviceRegistry()


def reset():
    REGISTRY.devices = []
    REGISTRY.removed = []


def add(device_id, identifiers):
    REGISTRY.devices.append(SimpleNamespace(id=device_id, identifiers=set(identifiers)))


def async_get(hass):
    return REGISTRY
