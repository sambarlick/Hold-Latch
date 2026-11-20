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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .area import discover_area_sources
from .const import (
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_EXCLUDE,
    CONF_HOLD_MODE,
    CONF_HOLD_TIME,
    CONF_HOLD_TYPE,
    CONF_LATCH_TRIGGER,
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
from .refs import resolve, resolve_all, to_ref, to_refs
from .repairs import AvailabilityWatcher, async_clear_hold_issues, async_raise_missing

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class RuntimeData:
    """Per-entry runtime data."""

    engines: dict[str, HoldEngine] = field(default_factory=dict)
    applied: dict[str, Any] = field(default_factory=dict)
    # Entity IDs each hold depends on directly (sensor-hold source, doors).
    tracked: dict[str, set[str]] = field(default_factory=dict)


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


@callback
def _async_store_refs(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> None:
    """Store entity registry IDs instead of entity IDs (holds from v0.6 and older).

    Runs before the update listener is added, so it doesn't trigger a reload.
    """
    for subentry in _holds(entry).values():
        data = dict(subentry.data)
        if source := data.get(CONF_SOURCE_ENTITY):
            data[CONF_SOURCE_ENTITY] = to_ref(hass, source)
        if doors := door_entities(data):
            data.pop(CONF_DOOR_ENTITY, None)
            data[CONF_DOOR_ENTITIES] = to_refs(hass, doors)
        if exclude := data.get(CONF_EXCLUDE):
            data[CONF_EXCLUDE] = to_refs(hass, exclude)
        if data != dict(subentry.data):
            hass.config_entries.async_update_subentry(entry, subentry, data=data)


async def async_setup_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> bool:
    """Set up Hold & Latch."""
    runtime = RuntimeData()
    entry.runtime_data = runtime
    _async_store_refs(hass, entry)

    for subentry_id, subentry in _holds(entry).items():
        runtime.engines[subentry_id] = await _async_start_hold(hass, entry, subentry)
        _async_tidy_devices(hass, entry, subentry)

    runtime.applied = _structure(entry)

    @callback
    def _registry_updated(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        """Reload when a sensor or door a hold uses is renamed or deleted."""
        data = event.data
        if data["action"] == "create":
            return
        if data["action"] == "update" and "old_entity_id" not in data:
            return
        changed = {data["entity_id"], data.get("old_entity_id")}
        if any(changed & tracked for tracked in runtime.tracked.values()):
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _registry_updated)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _async_tidy_devices(
    hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
) -> None:
    """Keep a hold on its own device only.

    Holds from v0.8 and older could share their sensor's device; unlink them
    from it so the sensor's device is left as it was.
    """
    dev_reg = dr.async_get(hass)
    subentry_id = subentry.subentry_id
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if subentry_id not in device.config_entries_subentries.get(entry.entry_id, ()):
            continue
        if (DOMAIN, subentry_id) not in device.identifiers:
            dev_reg.async_update_device(
                device.id,
                remove_config_entry_id=entry.entry_id,
                remove_config_subentry_id=subentry_id,
            )


async def _async_start_hold(
    hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
) -> HoldEngine:
    data = subentry.data
    subentry_id = subentry.subentry_id
    hold = subentry.title

    # Fresh notices on each start: deleted entities are raised again below,
    # and unavailable ones after the watcher's delay.
    async_clear_hold_issues(hass, subentry_id)

    doors, missing_doors = resolve_all(hass, door_entities(data))
    for ref in missing_doors:
        async_raise_missing(hass, subentry_id, hold, "door", ref)

    engine = HoldEngine(
        hass,
        storage_id=subentry_id,
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

    watched = dict.fromkeys(doors, "door")

    if data[CONF_HOLD_TYPE] == TYPE_SENSOR:
        if source := resolve(hass, data[CONF_SOURCE_ENTITY]):
            engine.async_set_sources({source})
            watched[source] = "sensor"
        else:
            async_raise_missing(
                hass, subentry_id, hold, "sensor", data[CONF_SOURCE_ENTITY]
            )
    else:
        area_id = data[CONF_AREA]
        device_classes = data.get(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES)

        @callback
        def _refresh_sources(_event: Event | None = None) -> None:
            exclude, _gone = resolve_all(hass, data.get(CONF_EXCLUDE, []))
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

    entry.runtime_data.tracked[subentry_id] = set(watched)
    watcher = AvailabilityWatcher(hass, subentry_id, hold, watched)
    watcher.async_start()
    entry.async_on_unload(watcher.async_stop)
    return engine


async def _async_update_listener(
    hass: HomeAssistant, entry: HoldLatchConfigEntry
) -> None:
    """Apply hold time and latch trigger live; reload when holds are added, removed or edited."""
    runtime = entry.runtime_data
    if _structure(entry) == runtime.applied:
        for subentry_id, subentry in _holds(entry).items():
            engine = runtime.engines[subentry_id]
            engine.async_set_hold(
                int(subentry.data.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME))
            )
            engine.async_set_latch_trigger(
                subentry.data.get(CONF_LATCH_TRIGGER, TRIGGER_NEW_MOTION)
            )
        return

    # Forget the saved state and notices of holds that were deleted.
    for subentry_id in set(runtime.applied) - set(_holds(entry)):
        async_clear_hold_issues(hass, subentry_id)
        if engine := runtime.engines.pop(subentry_id, None):
            await engine.async_remove_storage()
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> bool:
    """Unload Hold & Latch."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: HoldLatchConfigEntry) -> None:
    """Delete saved state and notices when the integration is removed."""
    for subentry_id in _holds(entry):
        async_clear_hold_issues(hass, subentry_id)
        await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{subentry_id}").async_remove()
