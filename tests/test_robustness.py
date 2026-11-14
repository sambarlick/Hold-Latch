"""Renames, repairs, manual controls and diagnostics."""

from datetime import timedelta

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.hold_latch.const import DOMAIN, SUBENTRY_HOLD
from custom_components.hold_latch.diagnostics import async_get_config_entry_diagnostics


async def _registered(hass, uid, cls, object_id):
    entry = er.async_get(hass).async_get_or_create(
        "binary_sensor",
        "zha",
        uid,
        original_device_class=cls,
        suggested_object_id=object_id,
    )
    hass.states.async_set(entry.entity_id, "off")
    return entry


async def _setup(hass, data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hold & Latch",
        data={},
        subentries_data=[
            {
                "subentry_type": SUBENTRY_HOLD,
                "title": "Ensuite",
                "data": data,
                "unique_id": None,
            }
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _sub(entry):
    return next(iter(entry.subentries.values()))


BASE = {
    "hold_type": "sensor_hold",
    "hold_time": 90,
    "hold_mode": "last_detected",
    "latch_when": "closed",
    "latch_trigger": "new_motion",
    "max_latch": 0,
}


async def test_old_entity_ids_are_stored_as_registry_ids(hass: HomeAssistant):
    """Holds saved with entity IDs are converted on startup."""
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    door = await _registered(hass, "d", "door", "ensuite_door")
    entry = await _setup(
        hass, {**BASE, "source_entity": motion.entity_id, "door_entity": door.entity_id}
    )
    data = _sub(entry).data
    assert data["source_entity"] == motion.id
    assert data["door_entities"] == [door.id]
    assert "door_entity" not in data


async def test_hold_survives_renames(hass: HomeAssistant):
    """Rename the motion sensor and the door: the hold and latch keep working."""
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    door = await _registered(hass, "d", "door", "ensuite_door")
    # Saved the old way, by entity ID: converted on startup, then renamed.
    await _setup(
        hass,
        {**BASE, "source_entity": motion.entity_id, "door_entities": [door.entity_id]},
    )

    reg = er.async_get(hass)
    reg.async_update_entity(motion.entity_id, new_entity_id="binary_sensor.ensuite_pir")
    reg.async_update_entity(
        door.entity_id, new_entity_id="binary_sensor.ensuite_door_contact"
    )
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.ensuite_pir", "off")
    hass.states.async_set("binary_sensor.ensuite_door_contact", "off")  # closed
    await hass.async_block_till_done()

    hass.states.async_set("binary_sensor.ensuite_pir", "on")
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.ensuite_occupancy")
    assert state.state == "on"
    assert state.attributes["sources"] == ["binary_sensor.ensuite_pir"]
    assert state.attributes["latched"] is True


async def test_deleted_sensor_raises_repair(hass: HomeAssistant):
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    entry = await _setup(hass, {**BASE, "source_entity": motion.id})
    er.async_get(hass).async_remove(motion.entity_id)
    await hass.async_block_till_done()
    sub = _sub(entry)
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"{sub.subentry_id}_missing_{motion.id}"
    )
    assert issue is not None
    assert issue.translation_key == "missing_sensor"


async def test_unavailable_door_repair_raised_and_cleared(hass: HomeAssistant, freezer):
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    door = await _registered(hass, "d", "door", "ensuite_door")
    entry = await _setup(
        hass, {**BASE, "source_entity": motion.id, "door_entities": [door.id]}
    )
    issue_id = f"{_sub(entry).subentry_id}_unavailable_{door.entity_id}"

    hass.states.async_set(door.entity_id, "unavailable")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=29))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, issue_id).translation_key
        == "unavailable_door"
    )

    hass.states.async_set(door.entity_id, "off")
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_release_latch_button(hass: HomeAssistant, freezer):
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    door = await _registered(hass, "d", "door", "ensuite_door")
    await _setup(hass, {**BASE, "source_entity": motion.id, "door_entities": [door.id]})
    hass.states.async_set(motion.entity_id, "on")
    hass.states.async_set(motion.entity_id, "off")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ensuite_latch").state == "on"

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.ensuite_release_latch"}, blocking=True
    )
    assert hass.states.get("binary_sensor.ensuite_latch").state == "off"
    assert (
        hass.states.get("binary_sensor.ensuite_occupancy").state == "on"
    )  # hold runs out
    freezer.tick(timedelta(seconds=91))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ensuite_occupancy").state == "off"


async def test_no_release_button_without_door(hass: HomeAssistant):
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    await _setup(hass, {**BASE, "source_entity": motion.id})
    assert hass.states.get("button.ensuite_release_latch") is None


async def test_force_occupied_switch(hass: HomeAssistant, freezer):
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    await _setup(hass, {**BASE, "source_entity": motion.id})
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.ensuite_force_occupied"},
        blocking=True,
    )
    freezer.tick(timedelta(hours=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ensuite_occupancy").state == "on"
    assert (
        hass.states.get("binary_sensor.ensuite_occupancy").attributes["forced"] is True
    )
    assert hass.states.get("sensor.ensuite_hold_ends").state == "unknown"

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.ensuite_force_occupied"},
        blocking=True,
    )
    assert (
        hass.states.get("binary_sensor.ensuite_occupancy").state == "on"
    )  # hold from now
    freezer.tick(timedelta(seconds=91))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ensuite_occupancy").state == "off"


async def test_diagnostics(hass: HomeAssistant):
    motion = await _registered(hass, "m", "motion", "ensuite_motion")
    door = await _registered(hass, "d", "door", "ensuite_door")
    entry = await _setup(
        hass, {**BASE, "source_entity": motion.id, "door_entities": [door.id]}
    )
    diag = await async_get_config_entry_diagnostics(hass, entry)
    hold = diag["holds"]["Ensuite"]
    assert hold["state"]["doors"] == {door.entity_id: False}
    assert hold["state"]["door_in_latch_position"] is True
    assert hold["entity_states"] == {motion.entity_id: "off", door.entity_id: "off"}
    assert hold["repairs"] == []
