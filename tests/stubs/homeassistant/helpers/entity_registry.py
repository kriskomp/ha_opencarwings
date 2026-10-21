"""Stub of homeassistant.helpers.entity_registry with an inspectable registry."""
from types import SimpleNamespace


class FakeRegistry:
    def __init__(self):
        self.entities = []
        self.removed = []

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.entities = [e for e in self.entities if e.entity_id != entity_id]


REGISTRY = FakeRegistry()


def reset():
    REGISTRY.entities = []
    REGISTRY.removed = []


def add(entity_id, config_entry_id, unique_id=None):
    REGISTRY.entities.append(
        SimpleNamespace(entity_id=entity_id, domain=entity_id.split(".")[0], config_entry_id=config_entry_id,
                        unique_id=unique_id)
    )


def async_get(hass):
    return REGISTRY


def async_entries_for_config_entry(registry, config_entry_id):
    return [e for e in registry.entities if e.config_entry_id == config_entry_id]
