"""Clears-at timestamp sensor for Hold & Latch."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    """Set up the clears-at sensor."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id in entry.runtime_data.engines:
            async_add_entities(
                [HoldLatchClearsAtSensor(hass, entry, subentry)],
                config_subentry_id=subentry_id,
            )


class HoldLatchClearsAtSensor(HoldLatchEntity, SensorEntity):
    """When the hold will clear.

    A timestamp rather than a countdown: the frontend shows it as
    "in 47 seconds" without writing a new state every second.
    Unknown while a source is on or the room is latched.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP


    def __init__(
        self, hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialise the sensor."""
        super().__init__(hass, entry, subentry, "clears_at")

    @property
    def native_value(self) -> datetime | None:
        """Return the clear time."""
        return self._engine.clears_at if self._engine.occupied else None
