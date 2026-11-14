"""Hold & Latch: occupancy holds and door latches for Home Assistant.

One config entry holds everything. Each hold is a config subentry with its
own device, engine and entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from .area import discover_area_sources
from .const import (
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_LATCH_TRIGGER,
    CONF_EXCLUDE,
    CONF_HOLD_MODE,
    CONF_HOLD_TIME,
    CONF_HOLD_TYPE,
    CONF_LATCH_WHEN,
    CONF_MAX_LATCH,
    CONF_SOURCE_ENTITY,
    DEFAULT_DEVICE_CLASSES,
    DEFAULT_HOLD_TIME,
    DEFAULT_MAX_LATCH,
    DOMAIN,
    LATCH_WHEN_CLOSED,
    LIVE_OPTIONS,
    MODE_LAST_DETECTED,
    STORAGE_VERSION,
    SUBENTRY_HOLD,
    TRIGGER_NEW_MOTION,
    TYPE_SENSOR,
    door_entities,
)
from .engine import HoldEngine
from .entity import attached_device_id

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]


@dataclass
class RuntimeData:
    """Per-entry runtime data."""

    engines: dict[str, HoldEngine] = field(default_factory=dict)
    applied: dict[str, Any] = field(default_factory=dict)


type HoldLatchConfigEntry = ConfigEntry[RuntimeData]


def _holds(entry: ConfigEntry) -> dict[str, ConfigSubentry]:
    return {
        subentry_id: subentry
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_HOLD
    }


def _structure(entry: ConfigEntry) -> dict[str, Any]:
    """Everything that needs a reload when it changes (not the hold time)."""
    return {
        subentry_id: (
            subentry.title,
            {k: v for k, v in subentry.data.items() if k not in LIVE_OPTIONS},
        )
        for subentry_id, subentry in _holds(entry).items()
    }


async def async_setup_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> bool:
    """Set up Hold & Latch."""
    runtime = RuntimeData()
    entry.runtime_data = runtime

    for subentry_id, subentry in _holds(entry).items():
        runtime.engines[subentry_id] = await _async_start_hold(hass, entry, subentry)
        _async_tidy_devices(hass, entry, subentry)

    runtime.applied = _structure(entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _async_tidy_devices(
    hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
) -> None:
    """Keep a hold linked to exactly one device.

    Attached to its sensor's device: drop the hold's own device. Not attached
    (or attached to a different sensor now): unlink from other devices.
    """
    dev_reg = dr.async_get(hass)
    subentry_id = subentry.subentry_id
    attached = attached_device_id(hass, subentry)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if subentry_id not in device.config_entries_subentries.get(entry.entry_id, ()):
            continue
        own = (DOMAIN, subentry_id) in device.identifiers
        if own and attached:
            dev_reg.async_remove_device(device.id)
        elif not own and device.id != attached:
            dev_reg.async_update_device(
                device.id,
                remove_config_entry_id=entry.entry_id,
                remove_config_subentry_id=subentry_id,
            )


async def _async_start_hold(
    hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
) -> HoldEngine:
    data = subentry.data
    doors = door_entities(data)

    engine = HoldEngine(
        hass,
        storage_id=subentry.subentry_id,
        hold_seconds=int(data.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME)),
        hold_mode=data.get(CONF_HOLD_MODE, MODE_LAST_DETECTED),
        door_entities=doors,
        latch_when=data.get(CONF_LATCH_WHEN, LATCH_WHEN_CLOSED),
        latch_trigger=data.get(CONF_LATCH_TRIGGER, TRIGGER_NEW_MOTION),
        max_latch_seconds=int(data.get(CONF_MAX_LATCH, DEFAULT_MAX_LATCH)),
    )
    await engine.async_load()
    engine.async_start()
    entry.async_on_unload(engine.async_stop)

    if data[CONF_HOLD_TYPE] == TYPE_SENSOR:
        engine.async_set_sources({data[CONF_SOURCE_ENTITY]})
        return engine

    area_id = data[CONF_AREA]
    device_classes = data.get(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES)
    exclude = data.get(CONF_EXCLUDE, [])

    @callback
    def _refresh_sources(_event: Event | None = None) -> None:
        engine.async_set_sources(
            discover_area_sources(hass, area_id, device_classes, exclude, doors)
        )

    _refresh_sources()
    # Re-discover when entities or devices are added, removed or moved.
    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _refresh_sources)
    )
    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _refresh_sources)
    )
    return engine


async def _async_update_listener(
    hass: HomeAssistant, entry: HoldLatchConfigEntry
) -> None:
    """Apply hold-time changes live; reload when holds are added, removed or edited."""
    runtime = entry.runtime_data
    if _structure(entry) == runtime.applied:
        for subentry_id, subentry in _holds(entry).items():
            runtime.engines[subentry_id].async_set_hold(
                int(subentry.data.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME))
            )
        return

    # Forget the saved state of holds that were deleted.
    for subentry_id in set(runtime.applied) - set(_holds(entry)):
        if engine := runtime.engines.pop(subentry_id, None):
            await engine.async_remove_storage()
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> bool:
    """Unload Hold & Latch."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> None:
    """Delete saved state when the integration is removed."""
    for subentry_id in _holds(entry):
        await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{subentry_id}").async_remove()
