"""Hold & Latch: VALLHORN-style occupancy holds and door latches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .area import discover_area_sources
from .const import (
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_DOOR_ACTIVE,
    CONF_DOOR_ENTITY,
    CONF_EXCLUDE,
    CONF_HOLD_MODE,
    CONF_HOLD_TIME,
    CONF_HOLD_TYPE,
    CONF_MAX_LATCH,
    CONF_SOURCE_ENTITY,
    DEFAULT_DEVICE_CLASSES,
    DEFAULT_HOLD_TIME,
    DEFAULT_MAX_LATCH,
    DOOR_ACTIVE_OPEN,
    LIVE_OPTIONS,
    MODE_LAST_DETECTED,
    TYPE_SENSOR,
)
from .engine import HoldEngine

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]


@dataclass
class RuntimeData:
    """Per-entry runtime data."""

    engine: HoldEngine
    applied_options: dict[str, Any]


type HoldLatchConfigEntry = ConfigEntry[RuntimeData]


def _structural(options: dict[str, Any]) -> dict[str, Any]:
    """Options that need a reload when they change."""
    return {key: value for key, value in options.items() if key not in LIVE_OPTIONS}


async def async_setup_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> bool:
    """Set up an Hold & Latch entry."""
    options = entry.options
    door_entity = options.get(CONF_DOOR_ENTITY)

    engine = HoldEngine(
        hass,
        entry_id=entry.entry_id,
        hold_seconds=int(options.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME)),
        hold_mode=options.get(CONF_HOLD_MODE, MODE_LAST_DETECTED),
        door_entity=door_entity,
        door_active=options.get(CONF_DOOR_ACTIVE, DOOR_ACTIVE_OPEN),
        max_latch_seconds=int(options.get(CONF_MAX_LATCH, DEFAULT_MAX_LATCH)),
    )
    await engine.async_load()
    engine.async_start()
    entry.async_on_unload(engine.async_stop)

    if entry.data[CONF_HOLD_TYPE] == TYPE_SENSOR:
        engine.async_set_sources({options[CONF_SOURCE_ENTITY]})
    else:
        area_id = options[CONF_AREA]
        device_classes = options.get(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES)
        exclude = options.get(CONF_EXCLUDE, [])

        @callback
        def _refresh_sources(_event: Event | None = None) -> None:
            engine.async_set_sources(
                discover_area_sources(hass, area_id, device_classes, exclude, door_entity)
            )

        _refresh_sources()
        # Re-discover when entities or devices are added, removed or moved.
        entry.async_on_unload(
            hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _refresh_sources)
        )
        entry.async_on_unload(
            hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _refresh_sources)
        )

    entry.runtime_data = RuntimeData(engine, _structural(dict(options)))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: HoldLatchConfigEntry
) -> None:
    """Apply hold-time changes live; reload for anything structural."""
    runtime = entry.runtime_data
    if _structural(dict(entry.options)) == runtime.applied_options:
        runtime.engine.async_set_hold(
            int(entry.options.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME))
        )
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
