"""Registry tidying: leftovers of removed entities and door buttons whose ids say the opposite action."""
from custom_components.ha_opencarwings import DOMAIN, cleanup
from homeassistant.helpers import device_registry as dr_stub
from homeassistant.helpers import entity_registry as er_stub

VIN = "VIN1"
DOOR_LOCK_UID = f"ha_opencarwings_car_doorlock_{VIN}"      # command 7 = unlock (old, swapped name)
DOOR_UNLOCK_UID = f"ha_opencarwings_car_doorunlock_{VIN}"  # command 8 = lock


def _fresh():
    er_stub.reset()
    dr_stub.reset()


def _ids():
    return sorted(e.entity_id for e in er_stub.REGISTRY.entities)


def _id_of(unique_id):
    return er_stub.REGISTRY.async_get_entity_id("button", DOMAIN, unique_id)


def test_removed_entities_are_dropped_from_the_registry():
    _fresh()
    er_stub.add("button.opencarwings_refresh", "e1", unique_id="ha_opencarwings_refresh_e1")
    er_stub.add("sensor.opencarwings_cars", "e1", unique_id="ha_opencarwings_e1_cars")
    er_stub.add("sensor.leaf_last_requested", "e1", unique_id=f"ha_opencarwings_last_requested_{VIN}")
    er_stub.add("sensor.leaf_vehicle_health_report", "e1", unique_id=f"ha_opencarwings_veh_health_report_{VIN}")
    er_stub.add("sensor.leaf_vin", "e1", unique_id=f"ha_opencarwings_vin_{VIN}")  # stays
    removed = cleanup.remove_stale_entities(er_stub.REGISTRY, "e1", [VIN])
    assert sorted(removed) == [
        "button.opencarwings_refresh", "sensor.leaf_last_requested",
        "sensor.leaf_vehicle_health_report", "sensor.opencarwings_cars",
    ]
    assert _ids() == ["sensor.leaf_vin"]


def test_only_the_first_car_keeps_the_push_connection_sensor():
    _fresh()
    er_stub.add("binary_sensor.a_push", "e1", unique_id="ha_opencarwings_push_VIN1")
    er_stub.add("binary_sensor.b_push", "e1", unique_id="ha_opencarwings_push_VIN2")
    cleanup.remove_stale_entities(er_stub.REGISTRY, "e1", ["VIN1", "VIN2"])
    assert _ids() == ["binary_sensor.a_push"]


def test_nameless_device_is_removed_only_when_empty():
    _fresh()
    dr_stub.add("dev1", {(DOMAIN, "")})
    er_stub.add("button.x", "e1", unique_id="u", device_id="dev1")
    assert cleanup.remove_nameless_entry_device(dr_stub.REGISTRY, er_stub.REGISTRY, er_stub) is False
    er_stub.REGISTRY.async_remove("button.x")
    assert cleanup.remove_nameless_entry_device(dr_stub.REGISTRY, er_stub.REGISTRY, er_stub) is True
    assert dr_stub.REGISTRY.removed == ["dev1"]
    assert cleanup.remove_nameless_entry_device(dr_stub.REGISTRY, er_stub.REGISTRY, er_stub) is False


def test_swapped_door_ids_are_fixed_when_the_unlock_button_holds_the_suffix():
    # The user's registry: both ids say "unlock"; the one for the lock command carries no suffix.
    _fresh()
    er_stub.add("button.leaf_unlock_doors_for_leaf", "e1", unique_id=DOOR_UNLOCK_UID)    # command 8 (lock)
    er_stub.add("button.leaf_unlock_doors_for_leaf_2", "e1", unique_id=DOOR_LOCK_UID)    # command 7 (unlock)
    done = cleanup.fix_door_entity_ids(er_stub.REGISTRY, [VIN])
    assert _id_of(DOOR_LOCK_UID) == "button.leaf_unlock_doors_for_leaf"
    assert _id_of(DOOR_UNLOCK_UID) == "button.leaf_lock_doors_for_leaf"
    assert len(done) == 2


def test_door_ids_are_fixed_when_the_lock_button_holds_the_suffix():
    _fresh()
    er_stub.add("button.leaf_unlock_doors_for_leaf", "e1", unique_id=DOOR_LOCK_UID)      # command 7, right word
    er_stub.add("button.leaf_unlock_doors_for_leaf_2", "e1", unique_id=DOOR_UNLOCK_UID)  # command 8, wrong word
    cleanup.fix_door_entity_ids(er_stub.REGISTRY, [VIN])
    assert _id_of(DOOR_LOCK_UID) == "button.leaf_unlock_doors_for_leaf"
    assert _id_of(DOOR_UNLOCK_UID) == "button.leaf_lock_doors_for_leaf"


def test_door_ids_that_are_already_right_are_left_alone():
    _fresh()
    er_stub.add("button.leaf_unlock_doors_for_leaf", "e1", unique_id=DOOR_LOCK_UID)
    er_stub.add("button.leaf_lock_doors_for_leaf", "e1", unique_id=DOOR_UNLOCK_UID)
    assert cleanup.fix_door_entity_ids(er_stub.REGISTRY, [VIN]) == []
    assert _ids() == ["button.leaf_lock_doors_for_leaf", "button.leaf_unlock_doors_for_leaf"]


def test_door_ids_the_user_renamed_are_left_alone():
    _fresh()
    er_stub.add("button.front_door_open", "e1", unique_id=DOOR_LOCK_UID)
    er_stub.add("button.front_door_close", "e1", unique_id=DOOR_UNLOCK_UID)
    assert cleanup.fix_door_entity_ids(er_stub.REGISTRY, [VIN]) == []


def test_a_number_that_belongs_to_the_car_name_is_not_stripped():
    _fresh()
    er_stub.add("button.leaf_2_unlock_doors_for_leaf_2", "e1", unique_id=DOOR_LOCK_UID)
    er_stub.add("button.leaf_2_lock_doors_for_leaf_2", "e1", unique_id=DOOR_UNLOCK_UID)
    assert cleanup.fix_door_entity_ids(er_stub.REGISTRY, [VIN]) == []


def test_a_taken_id_keeps_the_old_one():
    _fresh()
    er_stub.add("button.leaf_unlock_doors_for_leaf", "e1", unique_id=DOOR_UNLOCK_UID)    # command 8 (lock)
    er_stub.add("button.leaf_lock_doors_for_leaf", "other", unique_id="x", platform="other_integration")
    cleanup.fix_door_entity_ids(er_stub.REGISTRY, [VIN])
    assert _id_of(DOOR_UNLOCK_UID) == "button.leaf_unlock_doors_for_leaf"
    assert er_stub.REGISTRY.async_get("button.leaf_lock_doors_for_leaf").unique_id == "x"
