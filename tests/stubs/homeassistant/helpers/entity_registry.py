"""Stub of homeassistant.helpers.entity_registry with an inspectable registry."""
from types import SimpleNamespace


class FakeRegistry:
    def __init__(self):
        self.entities = []
        self.removed = []

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.entities = [e for e in self.entities if e.entity_id != entity_id]

    def async_get(self, entity_id):
        for e in self.entities:
            if e.entity_id == entity_id:
                return e
        return None

    def async_get_entity_id(self, domain, platform, unique_id):
        for e in self.entities:
            if e.domain == domain and e.platform == platform and e.unique_id == unique_id:
                return e.entity_id
        return None

    def async_update_entity(self, entity_id, new_entity_id=None, **kwargs):
        entity = self.async_get(entity_id)
        if entity is None:
            raise KeyError(entity_id)
        if new_entity_id is not None:
            if self.async_get(new_entity_id) is not None:
                raise ValueError(f"Entity with this ID is already registered: {new_entity_id}")
            entity.entity_id = new_entity_id
        return entity


REGISTRY = FakeRegistry()


def reset():
    REGISTRY.entities = []
    REGISTRY.removed = []


def add(entity_id, config_entry_id, unique_id=None, platform="ha_opencarwings", device_id=None):
    REGISTRY.entities.append(
        SimpleNamespace(entity_id=entity_id, domain=entity_id.split(".")[0], config_entry_id=config_entry_id,
                        unique_id=unique_id, platform=platform, device_id=device_id)
    )


def async_get(hass):
    return REGISTRY


def async_entries_for_config_entry(registry, config_entry_id):
    return [e for e in registry.entities if e.config_entry_id == config_entry_id]


def async_entries_for_device(registry, device_id, include_disabled_entities=False):
    return [e for e in registry.entities if e.device_id == device_id]
