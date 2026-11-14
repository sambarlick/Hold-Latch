"""Occupancy binary sensor for Hold & Latch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HoldLatchConfigEntry
from .entity import HoldLatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HoldLatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the occupancy sensor."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id in entry.runtime_data.engines:
            async_add_entities(
                [HoldLatchBinarySensor(hass, entry, subentry)],
                config_subentry_id=subentry_id,
            )


class HoldLatchBinarySensor(HoldLatchEntity, BinarySensorEntity):
    """Held occupancy."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    # Keep fast-changing / bulky attributes out of the recorder.
    _unrecorded_attributes = frozenset({"sources", "last_detected"})

    _attached_translation_key = "hold"

    def __init__(
        self, hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialise the sensor."""
        super().__init__(hass, entry, subentry, "occupancy")

    @property
    def is_on(self) -> bool:
        """Return True if occupied."""
        return self._engine.occupied

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the reasoning behind the state."""
        engine = self._engine
        attrs: dict[str, Any] = {
            "motion": engine.any_source_on,
            "latched": engine.latched,
            "last_detected": engine.last_detected.isoformat()
            if engine.last_detected
            else None,
            "sources": sorted(engine.sources),
        }
        if engine.door_configured:
            attrs["door_open"] = engine.door_open
            attrs["latched_since"] = (
                engine.latched_since.isoformat() if engine.latched_since else None
            )
        return attrs
