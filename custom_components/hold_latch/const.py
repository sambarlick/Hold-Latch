"""Constants for Hold & Latch."""

from __future__ import annotations

DOMAIN = "hold_latch"
STORAGE_VERSION = 1

# Entry type (stored in entry.data)
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
CONF_DOOR_ENTITY = "door_entity"
CONF_DOOR_ACTIVE = "door_active"
CONF_MAX_LATCH = "max_latch"

# Hold modes
MODE_LAST_DETECTED = "last_detected"  # hold runs from the last motion onset
MODE_LAST_CLEAR = "last_clear"  # hold runs from when all sources clear

# Door polarity: what the door sensor's "on" state means
DOOR_ACTIVE_OPEN = "open"  # on = open (HA standard for door/opening)
DOOR_ACTIVE_CLOSED = "closed"  # on = closed (inverted contact)

DEFAULT_HOLD_TIME = 90
DEFAULT_MAX_LATCH = 10800  # 3 hours; 0 disables
DEFAULT_DEVICE_CLASSES = ["motion", "occupancy"]
SUPPORTED_DEVICE_CLASSES = ["motion", "occupancy", "presence"]

MAX_HOLD_TIME = 7200
MAX_LATCH_LIMIT = 86400

# Options that can change without reloading the entry
LIVE_OPTIONS = frozenset({CONF_HOLD_TIME})
