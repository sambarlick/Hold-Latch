"""Base entity for Hold & Latch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

if TYPE_CHECKING:
    from . import HoldLatchConfigEntry


class HoldLatchEntity(Entity):
    """Common behaviour: one device per hold, push updates from the engine."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: HoldLatchConfigEntry, key: str) -> None:
        """Initialise the entity."""
        self._entry = entry
        self._engine = entry.runtime_data.engine
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Hold & Latch",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to engine updates."""
        self.async_on_remove(self._engine.async_add_listener(self.async_write_ha_state))
