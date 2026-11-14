"""Constants for Hold & Latch."""

from __future__ import annotations

DOMAIN = "hold_latch"
STORAGE_VERSION = 1

SUBENTRY_HOLD = "hold"

# Hold type (stored in each hold's data)
CONF_HOLD_TYPE = "hold_type"
TYPE_SENSOR = "sensor_hold"
TYPE_AREA = "area_hold"

# Options
CONF_NAME = "name"
CONF_SOURCE_ENTITY = "source_entity"
CONF_AREA = "area"
CONF_DEVICE_CLASSES = "device_classes"
CONF_EXCLUDE = "exclude_entities"
CONF_HOLD_TIME = "hold_time"
CONF_HOLD_MODE = "hold_mode"
CONF_ADD_LATCH = "add_latch"
CONF_ATTACH = "attach_to_sensor"
CONF_DOOR_ENTITY = "door_entity"  # v0.1-0.4: one door
CONF_DOOR_ENTITIES = "door_entities"
CONF_LATCH_TRIGGER = "latch_trigger"
CONF_LATCH_WHEN = "latch_when"
CONF_MAX_LATCH = "max_latch"

# Hold modes
MODE_LAST_DETECTED = "last_detected"  # hold runs from the last motion onset
MODE_LAST_CLEAR = "last_clear"  # hold runs from when all sources clear

# Which door position holds the latch
LATCH_WHEN_CLOSED = "closed"  # latched while the door is shut (ensuite, toilet)
LATCH_WHEN_OPEN = "open"  # latched while the door is open

# What starts the latch once the door(s) are in the latch position
TRIGGER_NEW_MOTION = "new_motion"  # motion that starts after (safest)
TRIGGER_MOTION_PRESENT = "motion_present"  # also motion already showing
TRIGGER_DOOR_ONLY = "door_only"  # no motion needed (e.g. a garage door left open)


def door_entities(data) -> list[str]:
    """Doors for a hold, reading the old single-door key too."""
    if doors := data.get(CONF_DOOR_ENTITIES):
        return list(doors)
    if door := data.get(CONF_DOOR_ENTITY):
        return [door]
    return []


# Entity filters for the setup selectors
SOURCE_DEVICE_CLASSES = ["motion", "occupancy"]
DOOR_DEVICE_CLASSES = ["door", "garage_door", "opening"]

DEFAULT_HOLD_TIME = 90
DEFAULT_MAX_LATCH = 10800  # 3 hours; 0 disables
DEFAULT_DEVICE_CLASSES = ["motion", "occupancy"]
SUPPORTED_DEVICE_CLASSES = ["motion", "occupancy", "presence"]

MAX_HOLD_TIME = 7200
MAX_LATCH_LIMIT = 86400

# Options that can change without reloading the entry
LIVE_OPTIONS = frozenset({CONF_HOLD_TIME})
