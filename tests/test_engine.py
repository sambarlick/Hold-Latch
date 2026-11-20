"""Behaviour tests for Hold & Latch."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from custom_components.hold_latch.const import (
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_DOOR_ENTITY,
    CONF_HOLD_MODE,
    CONF_HOLD_TIME,
    CONF_HOLD_TYPE,
    CONF_DOOR_ENTITIES,
    CONF_LATCH_TRIGGER,
    CONF_LATCH_WHEN,
    CONF_MAX_LATCH,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    LATCH_WHEN_CLOSED,
    LATCH_WHEN_OPEN,
    MODE_LAST_CLEAR,
    MODE_LAST_DETECTED,
    SUBENTRY_HOLD,
    TYPE_AREA,
    TYPE_SENSOR,
)

MOTION = "binary_sensor.test_motion"
DOOR = "binary_sensor.test_door"
HOLD = "binary_sensor.test_hold_occupancy"
CLEARS = "sensor.test_hold_hold_ends"
NUMBER = "number.test_hold_hold_time"


async def _setup(hass, *, hold_type=TYPE_SENSOR, **options):
    data = {
        CONF_HOLD_TYPE: hold_type,
        CONF_HOLD_TIME: 90,
        CONF_HOLD_MODE: MODE_LAST_DETECTED,
        CONF_LATCH_WHEN: LATCH_WHEN_CLOSED,
        CONF_MAX_LATCH: 0,
        **options,
    }
    if hold_type == TYPE_SENSOR:
        data.setdefault(CONF_SOURCE_ENTITY, MOTION)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hold & Latch",
        data={},
        subentries_data=[
            {
                "subentry_type": SUBENTRY_HOLD,
                "title": "Test hold",
                "data": data,
                "unique_id": None,
            }
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set(hass, entity_id, state):
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


async def _tick(hass, freezer: FrozenDateTimeFactory, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _on(hass, entity_id=HOLD):
    return hass.states.get(entity_id).state == "on"


# ---------------------------------------------------------------- holds


async def test_vallhorn_style_hold(hass: HomeAssistant, freezer):
    """Hold runs 90 s from the last onset, like the VALLHORN."""
    await _set(hass, MOTION, "off")
    await _setup(hass)
    assert not _on(hass)

    await _set(hass, MOTION, "on")
    assert _on(hass)
    # Clear time is known straight away and doesn't change when motion clears.
    clears = hass.states.get(CLEARS).state
    assert clears not in ("unknown", "unavailable")
    await _tick(hass, freezer, 20)
    await _set(hass, MOTION, "off")  # raw motion clears at +20 s
    assert _on(hass)
    assert hass.states.get(CLEARS).state == clears

    await _tick(hass, freezer, 69)  # +89 s
    assert _on(hass)
    await _tick(hass, freezer, 2)  # +91 s
    assert not _on(hass)
    assert hass.states.get(CLEARS).state == "unknown"


async def test_retrigger_extends(hass: HomeAssistant, freezer):
    """A new onset restarts the hold (the 09:56:20 / 09:57:17 case)."""
    await _set(hass, MOTION, "off")
    await _setup(hass)
    await _set(hass, MOTION, "on")
    await _tick(hass, freezer, 20)
    await _set(hass, MOTION, "off")
    await _tick(hass, freezer, 37)  # +57 s: motion again
    await _set(hass, MOTION, "on")
    await _tick(hass, freezer, 18)
    await _set(hass, MOTION, "off")
    await _tick(hass, freezer, 70)  # 88 s after the second onset
    assert _on(hass)
    await _tick(hass, freezer, 3)
    assert not _on(hass)


async def test_last_clear_mode(hass: HomeAssistant, freezer):
    """In last_clear mode the hold counts from when the source clears."""
    await _set(hass, MOTION, "off")
    await _setup(hass, **{CONF_HOLD_MODE: MODE_LAST_CLEAR, CONF_HOLD_TIME: 30})
    await _set(hass, MOTION, "on")
    await _tick(hass, freezer, 600)  # presence sensor on for 10 min
    await _set(hass, MOTION, "off")
    await _tick(hass, freezer, 29)
    assert _on(hass)
    await _tick(hass, freezer, 2)
    assert not _on(hass)


async def test_live_hold_change(hass: HomeAssistant, freezer):
    """Changing the number applies without a reload."""
    await _set(hass, MOTION, "off")
    entry = await _setup(hass)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": NUMBER, "value": 10}, blocking=True
    )
    await hass.async_block_till_done()
    assert next(iter(entry.subentries.values())).data[CONF_HOLD_TIME] == 10
    assert hass.states.get(NUMBER).state == "10"

    await _set(hass, MOTION, "on")
    await _set(hass, MOTION, "off")
    await _tick(hass, freezer, 11)
    assert not _on(hass)


# ---------------------------------------------------------------- latch


async def test_latch_after_door_closes(hass: HomeAssistant, freezer):
    """Door closed + new motion after it closed = latched until door opens."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "on")  # open
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})

    await _set(hass, MOTION, "on")  # walk in
    await _set(hass, DOOR, "off")  # close door behind you
    await _set(hass, MOTION, "off")
    await _set(hass, MOTION, "on")  # move inside: new onset after close
    await _set(hass, MOTION, "off")
    attrs = hass.states.get(HOLD).attributes
    assert attrs["latched"] is True

    await _tick(hass, freezer, 3600)  # sit still for an hour
    assert _on(hass)

    await _set(hass, DOOR, "on")  # leave
    assert hass.states.get(HOLD).attributes["latched"] is False
    assert _on(hass)  # hold restarts from the door opening
    await _tick(hass, freezer, 91)
    assert not _on(hass)


async def test_no_false_latch_on_exit(hass: HomeAssistant, freezer):
    """Leaving and closing the door must not latch an empty room."""
    await _set(hass, MOTION, "on")  # still on from your exit
    await _set(hass, DOOR, "on")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})

    await _set(hass, DOOR, "off")  # door closes behind you
    await _tick(hass, freezer, 5)
    await _set(hass, MOTION, "off")  # sensor hold lapses, no new onset
    assert hass.states.get(HOLD).attributes["latched"] is False
    await _tick(hass, freezer, 91)
    assert not _on(hass)


async def test_latch_while_door_open(hass: HomeAssistant, freezer):
    """latch_when=open: latched while open, released when the door closes."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "off")  # closed
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR, CONF_LATCH_WHEN: LATCH_WHEN_OPEN})
    await _set(hass, MOTION, "on")  # closed door: no latch
    await _set(hass, MOTION, "off")
    assert hass.states.get(HOLD).attributes["latched"] is False

    await _set(hass, DOOR, "on")  # open = latch position
    await _set(hass, MOTION, "on")
    assert hass.states.get(HOLD).attributes["latched"] is True
    assert hass.states.get(HOLD).attributes["door_open"] is True
    await _set(hass, DOOR, "off")  # closes
    assert hass.states.get(HOLD).attributes["latched"] is False


async def test_unavailable_door_blocks_new_latch(hass: HomeAssistant, freezer):
    """An unavailable door never creates a latch."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "unavailable")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    await _set(hass, MOTION, "on")
    await _set(hass, MOTION, "off")
    assert hass.states.get(HOLD).attributes["latched"] is False
    await _tick(hass, freezer, 91)
    assert not _on(hass)


async def test_unavailable_door_keeps_existing_latch(hass: HomeAssistant, freezer):
    """A door dropping offline doesn't release an existing latch."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "off")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    await _set(hass, MOTION, "on")
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "unavailable")
    await _tick(hass, freezer, 600)
    assert _on(hass)
    assert hass.states.get(HOLD).attributes["latched"] is True


async def test_source_back_from_unavailable_does_not_latch(
    hass: HomeAssistant, freezer
):
    """unavailable -> on (restart/reconnect) is not new motion."""
    await _set(hass, MOTION, "unavailable")
    await _set(hass, DOOR, "off")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    await _set(hass, MOTION, "on")
    assert hass.states.get(HOLD).attributes["latched"] is False
    assert _on(hass)


async def test_max_latch_releases(hass: HomeAssistant, freezer):
    """A stuck latch releases after max latch, then the hold runs out."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "off")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR, CONF_MAX_LATCH: 600})
    await _set(hass, MOTION, "on")
    await _set(hass, MOTION, "off")
    await _tick(hass, freezer, 599)
    assert hass.states.get(HOLD).attributes["latched"] is True
    await _tick(hass, freezer, 2)
    assert hass.states.get(HOLD).attributes["latched"] is False
    assert _on(hass)  # hold from release
    await _tick(hass, freezer, 91)
    assert not _on(hass)


# ---------------------------------------------------------------- area


async def test_area_discovery(hass: HomeAssistant, freezer):
    """Area hold picks up sensors via their device and follows registry changes."""
    area = ar.async_get(hass).async_create("Hallway")
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    other = MockConfigEntry(domain="zha")
    other.add_to_hass(hass)

    device = dev_reg.async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("zha", "pir")}
    )
    dev_reg.async_update_device(device.id, area_id=area.id)
    pir = ent_reg.async_get_or_create(
        "binary_sensor",
        "zha",
        "pir_motion",
        device_id=device.id,
        original_device_class="motion",
    )
    ent_reg.async_get_or_create(  # wrong class: ignored
        "binary_sensor",
        "zha",
        "pir_tamper",
        device_id=device.id,
        original_device_class="tamper",
    )
    hass.states.async_set(pir.entity_id, "off")

    await _setup(
        hass,
        hold_type=TYPE_AREA,
        **{CONF_AREA: area.id, CONF_DEVICE_CLASSES: ["motion", "occupancy"]},
    )
    assert hass.states.get(HOLD).attributes["sources"] == [pir.entity_id]
    # Our own occupancy sensor must never feed itself.
    assert HOLD not in hass.states.get(HOLD).attributes["sources"]

    await _set(hass, pir.entity_id, "on")
    assert _on(hass)

    # Add a second sensor directly to the area: picked up live.
    extra = ent_reg.async_get_or_create(
        "binary_sensor", "zha", "mmwave", original_device_class="occupancy"
    )
    ent_reg.async_update_entity(extra.entity_id, area_id=area.id)
    await hass.async_block_till_done()
    assert sorted(hass.states.get(HOLD).attributes["sources"]) == sorted(
        [pir.entity_id, extra.entity_id]
    )


# ---------------------------------------------------------------- multi / migration


async def test_two_holds_one_entry(hass: HomeAssistant, freezer):
    """Each hold is its own device under one integration entry."""
    hass.states.async_set("binary_sensor.a", "off")
    hass.states.async_set("binary_sensor.b", "off")
    base = {
        CONF_HOLD_TYPE: TYPE_SENSOR,
        CONF_HOLD_TIME: 30,
        CONF_HOLD_MODE: MODE_LAST_DETECTED,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        title="Hold & Latch",
        subentries_data=[
            {
                "subentry_type": SUBENTRY_HOLD,
                "title": "Room A",
                "data": {**base, CONF_SOURCE_ENTITY: "binary_sensor.a"},
                "unique_id": None,
            },
            {
                "subentry_type": SUBENTRY_HOLD,
                "title": "Room B",
                "data": {**base, CONF_SOURCE_ENTITY: "binary_sensor.b"},
                "unique_id": None,
            },
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _set(hass, "binary_sensor.a", "on")
    assert hass.states.get("binary_sensor.room_a_occupancy").state == "on"
    assert hass.states.get("binary_sensor.room_b_occupancy").state == "off"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(d.name for d in devices) == ["Room A", "Room B"]
    assert all(len(d.config_entries_subentries[entry.entry_id]) == 1 for d in devices)

    # Removing a hold removes its device and entities.
    sub_b = next(s for s in entry.subentries.values() if s.title == "Room B")
    hass.config_entries.async_remove_subentry(entry, sub_b.subentry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.room_b_occupancy") is None
    assert er.async_get(hass).async_get("binary_sensor.room_b_occupancy") is None
    assert hass.states.get("binary_sensor.room_a_occupancy").state == "on"


async def test_clears_at_unknown_when_motion_outlasts_hold(
    hass: HomeAssistant, freezer
):
    """Motion still on after the predicted time: Clears at becomes unknown."""
    await _set(hass, MOTION, "off")
    await _setup(hass, **{CONF_HOLD_TIME: 30})
    await _set(hass, MOTION, "on")
    assert hass.states.get(CLEARS).state != "unknown"
    await _tick(hass, freezer, 31)
    assert _on(hass)
    assert hass.states.get(CLEARS).state == "unknown"


async def test_clears_at_unknown_while_on_in_last_clear_mode(
    hass: HomeAssistant, freezer
):
    """When-motion-clears mode can't predict while motion is on."""
    await _set(hass, MOTION, "off")
    await _setup(hass, **{CONF_HOLD_MODE: MODE_LAST_CLEAR})
    await _set(hass, MOTION, "on")
    assert hass.states.get(CLEARS).state == "unknown"
    await _set(hass, MOTION, "off")
    assert hass.states.get(CLEARS).state != "unknown"


async def test_latch_entity(hass: HomeAssistant, freezer):
    """A hold with a door gets a Latch entity; one without doesn't."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "off")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    latch = "binary_sensor.test_hold_latch"
    assert hass.states.get(latch).state == "off"
    await _set(hass, MOTION, "on")
    assert hass.states.get(latch).state == "on"
    assert hass.states.get(latch).attributes["latched_since"] is not None
    await _set(hass, DOOR, "on")
    assert hass.states.get(latch).state == "off"


async def test_no_latch_entity_without_door(hass: HomeAssistant, freezer):
    await _set(hass, MOTION, "off")
    await _setup(hass)
    assert hass.states.get("binary_sensor.test_hold_latch") is None


# ---------------------------------------------------------------- triggers / many doors

GARAGE = [
    "binary_sensor.roller_door",
    "binary_sensor.side_door",
    "binary_sensor.house_door",
]


async def test_motion_present_trigger(hass: HomeAssistant, freezer):
    """motion_present: motion still showing when the door closes latches."""
    await _set(hass, MOTION, "on")
    await _set(hass, DOOR, "on")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR, CONF_LATCH_TRIGGER: "motion_present"})
    await _set(hass, DOOR, "off")
    assert hass.states.get(HOLD).attributes["latched"] is True


async def test_new_motion_trigger_ignores_motion_present(hass: HomeAssistant, freezer):
    """The default doesn't latch on motion already showing."""
    await _set(hass, MOTION, "on")
    await _set(hass, DOOR, "on")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    await _set(hass, DOOR, "off")
    assert hass.states.get(HOLD).attributes["latched"] is False


async def test_garage_any_door_open_door_only(hass: HomeAssistant, freezer):
    """Garage: any of three doors open latches, no motion needed."""
    for door in GARAGE:
        await _set(hass, door, "off")
    await _set(hass, MOTION, "off")
    await _setup(
        hass,
        **{
            CONF_DOOR_ENTITIES: GARAGE,
            CONF_LATCH_WHEN: LATCH_WHEN_OPEN,
            CONF_LATCH_TRIGGER: "door_only",
        },
    )
    assert not _on(hass)
    await _set(hass, GARAGE[1], "on")  # side door opens
    assert _on(hass)
    assert hass.states.get(HOLD).attributes["latched"] is True
    await _set(hass, GARAGE[0], "on")  # roller door too
    await _set(hass, GARAGE[1], "off")  # side door shut: roller still open
    assert hass.states.get(HOLD).attributes["latched"] is True
    await _set(hass, GARAGE[0], "off")  # all shut: release, hold runs out
    assert hass.states.get(HOLD).attributes["latched"] is False
    await _tick(hass, freezer, 91)
    assert not _on(hass)


async def test_door_only_latches_at_startup(hass: HomeAssistant, freezer):
    """door_only: already in position at startup -> latched."""
    await _set(hass, MOTION, "off")
    await _set(hass, GARAGE[0], "on")
    await _setup(
        hass,
        **{
            CONF_DOOR_ENTITIES: [GARAGE[0]],
            CONF_LATCH_WHEN: LATCH_WHEN_OPEN,
            CONF_LATCH_TRIGGER: "door_only",
        },
    )
    assert _on(hass)


async def test_several_doors_closed_needs_all_closed(hass: HomeAssistant, freezer):
    """Latch while closed with two doors: only once both are closed."""
    doors = ["binary_sensor.door_a", "binary_sensor.door_b"]
    await _set(hass, doors[0], "on")
    await _set(hass, doors[1], "on")
    await _set(hass, MOTION, "off")
    await _setup(hass, **{CONF_DOOR_ENTITIES: doors})
    await _set(hass, doors[0], "off")
    await _set(hass, MOTION, "on")  # one door still open: no latch
    await _set(hass, MOTION, "off")
    assert hass.states.get(HOLD).attributes["latched"] is False
    await _set(hass, doors[1], "off")
    await _set(hass, MOTION, "on")
    assert hass.states.get(HOLD).attributes["latched"] is True
    await _set(hass, doors[1], "on")
    assert hass.states.get(HOLD).attributes["latched"] is False


async def test_source_already_on_at_startup_still_holds(hass: HomeAssistant, freezer):
    """A source on at startup has no recorded onset; the hold must still run."""
    await _set(hass, MOTION, "on")
    await _setup(hass)
    assert hass.states.get(HOLD).attributes["last_detected"] is not None
    await _tick(hass, freezer, 10)
    await _set(hass, MOTION, "off")
    assert _on(hass)
    await _tick(hass, freezer, 81)
    assert not _on(hass)


# ------------------------------------------------------- live latch trigger

SELECT = "select.test_hold_latch_mode"


async def _select(hass, option):
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": option},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_latch_trigger_select_applies_live(hass: HomeAssistant, freezer):
    """The select changes the trigger without a reload and stores it."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "on")
    entry = await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    assert hass.states.get(SELECT).state == "new_motion"

    await _select(hass, "motion_present")
    assert hass.states.get(SELECT).state == "motion_present"
    assert next(iter(entry.subentries.values())).data[CONF_LATCH_TRIGGER] == (
        "motion_present"
    )

    # Night: you leave with motion still showing, the child stays in bed.
    await _set(hass, MOTION, "on")
    await _set(hass, DOOR, "off")
    assert hass.states.get(HOLD).attributes["latched"] is True


async def test_switch_to_motion_present_after_door_closed(
    hass: HomeAssistant, freezer
):
    """Switching just after the door closed, motion still on, latches now."""
    await _set(hass, MOTION, "on")
    await _set(hass, DOOR, "on")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    await _set(hass, DOOR, "off")
    assert hass.states.get(HOLD).attributes["latched"] is False

    await _select(hass, "motion_present")
    assert hass.states.get(HOLD).attributes["latched"] is True


async def test_switch_to_motion_present_empty_room_does_not_latch(
    hass: HomeAssistant, freezer
):
    """No motion showing at the switch: an empty closed room stays unlatched."""
    await _set(hass, MOTION, "off")
    await _set(hass, DOOR, "off")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR})
    await _select(hass, "motion_present")
    assert hass.states.get(HOLD).attributes["latched"] is False


async def test_switch_to_new_motion_keeps_latch(hass: HomeAssistant, freezer):
    """Morning switch back to New motion doesn't release an occupied room."""
    await _set(hass, MOTION, "on")
    await _set(hass, DOOR, "on")
    await _setup(hass, **{CONF_DOOR_ENTITY: DOOR, CONF_LATCH_TRIGGER: "motion_present"})
    await _set(hass, DOOR, "off")
    assert hass.states.get(HOLD).attributes["latched"] is True

    await _select(hass, "new_motion")
    await _set(hass, MOTION, "off")
    await _tick(hass, freezer, 3600)
    assert hass.states.get(HOLD).attributes["latched"] is True
    assert _on(hass)

    # By day, leaving and shutting the door no longer latches.
    await _set(hass, DOOR, "on")
    await _set(hass, MOTION, "on")
    await _set(hass, DOOR, "off")
    await _set(hass, MOTION, "off")
    assert hass.states.get(HOLD).attributes["latched"] is False


async def test_no_latch_trigger_select_without_door(hass: HomeAssistant, freezer):
    """Holds without a door have nothing to latch, so no select."""
    await _set(hass, MOTION, "off")
    await _setup(hass)
    assert hass.states.get(SELECT) is None
