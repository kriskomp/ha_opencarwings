"""One-off tidying of registry leftovers from earlier versions.

Runs at every start, before the platforms are set up, and only touches entries that are provably stale:

* entities and the nameless device of the removed account-level "OpenCARWINGS Refresh" button,
* the removed "Last Requested" and "Vehicle Health Report" sensors,
* duplicate "Push Connection" sensors (there is one connection per account, so one sensor),
* door buttons whose entity id says the opposite of what the button does.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Door buttons. The unique ids come from the first version of the integration, where the names were
# swapped: ``doorlock`` is command 7 (unlock) and ``doorunlock`` is command 8 (lock).
DOOR_UNIQUE_ID_ACTION = {"doorlock": "unlock", "doorunlock": "lock"}
_DOOR_WORDS = re.compile(r"(?:un)?lock_doors")
_NUMBER_SUFFIX = re.compile(r"_\d+$")


def stale_entities(entry_id: str, vins: list[str]) -> list[tuple[str, str]]:
    """``(domain, unique_id)`` of entities this version no longer creates."""
    stale = [
        ("button", f"ha_opencarwings_refresh_{entry_id}"),
        ("sensor", f"ha_opencarwings_{entry_id}_cars"),
    ]
    for vin in vins:
        stale.append(("sensor", f"ha_opencarwings_last_requested_{vin}"))
        stale.append(("sensor", f"ha_opencarwings_veh_health_report_{vin}"))
    # The live connection belongs to the account, not to a car: only the first car keeps its sensor.
    for vin in vins[1:]:
        stale.append(("binary_sensor", f"ha_opencarwings_push_{vin}"))
    return stale


def remove_stale_entities(registry: Any, entry_id: str, vins: list[str]) -> list[str]:
    removed = []
    for domain, unique_id in stale_entities(entry_id, vins):
        entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
        if entity_id is not None:
            registry.async_remove(entity_id)
            removed.append(entity_id)
    return removed


def remove_nameless_entry_device(device_registry: Any, entity_registry: Any, entity_registry_module: Any) -> bool:
    """Remove the empty device with the blank identifier ("no name") that held the account-level button.

    Only when nothing is left on it.
    """
    device = device_registry.async_get_device(identifiers={(DOMAIN, "")})
    if device is None:
        return False
    if entity_registry_module.async_entries_for_device(entity_registry, device.id, include_disabled_entities=True):
        return False
    device_registry.async_remove_device(device.id)
    return True


def door_entity_id_moves(registry: Any, vins: list[str]) -> list[tuple[str, str]]:
    """``(current, wanted)`` entity ids for door buttons whose id names the wrong action.

    Command 7 unlocks and command 8 locks. The registry keeps the id from the day the entity was created, so
    after the names were fixed an id can still say ``lock_doors`` for the button that unlocks. The id is only
    rewritten when it contains ``lock_doors``/``unlock_doors``; ids the user renamed freely are left alone.
    """
    found = []  # (entity_id, object_id, object_id with the right action word)
    for vin in vins:
        for infix, action in DOOR_UNIQUE_ID_ACTION.items():
            entity_id = registry.async_get_entity_id("button", DOMAIN, f"ha_opencarwings_car_{infix}_{vin}")
            if entity_id is None:
                continue
            object_id = entity_id.split(".", 1)[1]
            if not _DOOR_WORDS.search(object_id):
                continue
            found.append((entity_id, object_id, _DOOR_WORDS.sub(f"{action}_doors", object_id, count=1)))

    # Ids that stop being used because their button gets another one.
    vacated = {entity_id for entity_id, object_id, fixed in found if fixed != object_id}
    object_ids = {object_id for _entity_id, object_id, _fixed in found}
    claimed: set[str] = set()
    moves = []
    for entity_id, object_id, fixed in found:
        # A ``_2`` suffix comes from a clash with the other door button of the same car. Drop it only
        # when that sibling really holds the base id; a number that belongs to the car's name stays.
        base = _NUMBER_SUFFIX.sub("", object_id)
        suffix_from_clash = base != object_id and base in object_ids
        candidates = [_NUMBER_SUFFIX.sub("", fixed), fixed] if suffix_from_clash else [fixed]
        for candidate in dict.fromkeys(candidates):
            target = f"button.{candidate}"
            if target == entity_id:
                claimed.add(target)
                break
            if target in claimed:
                continue
            if registry.async_get(target) is None or target in vacated:
                claimed.add(target)
                moves.append((entity_id, target))
                break
    return moves


def fix_door_entity_ids(registry: Any, vins: list[str]) -> list[tuple[str, str]]:
    """Give the door buttons ids that match their action. Handles a swap and a clash with other entities.

    Every move goes through a temporary id first, so two buttons can swap ids. When the wanted id is taken by
    something else, the button gets its old id back.
    """
    moves = door_entity_id_moves(registry, vins)
    if not moves:
        return []
    temporary = {}
    for index, (current, _wanted) in enumerate(moves):
        temp_id = f"button.ha_opencarwings_migrating_{index}"
        registry.async_update_entity(current, new_entity_id=temp_id)
        temporary[current] = temp_id
    done = []
    for current, wanted in moves:
        temp_id = temporary[current]
        if registry.async_get(wanted) is None:
            registry.async_update_entity(temp_id, new_entity_id=wanted)
            done.append((current, wanted))
            _LOGGER.info("Renamed %s to %s (the id now matches what the button does)", current, wanted)
        else:
            registry.async_update_entity(temp_id, new_entity_id=current)
            _LOGGER.warning("Could not rename %s to %s: the id is taken", current, wanted)
    return done


def run_cleanup(hass: Any, entry_id: str, vins: list[str]) -> None:
    """Entry point from ``async_setup_entry``; never lets a registry problem break the setup."""
    try:
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        entity_registry = er.async_get(hass)
        remove_stale_entities(entity_registry, entry_id, vins)
        remove_nameless_entry_device(dr.async_get(hass), entity_registry, er)
        fix_door_entity_ids(entity_registry, vins)
    except Exception:  # noqa: BLE001 - tidying is best effort
        _LOGGER.exception("Registry cleanup failed")
