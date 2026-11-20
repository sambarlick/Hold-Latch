"""Release-latch button for Hold & Latch."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Add a Release latch button to holds with a door latch."""
    for subentry_id, subentry in entry.subentries.items():
        engine = entry.runtime_data.engines.get(subentry_id)
        if engine and engine.door_configured:
            async_add_entities(
                [HoldLatchReleaseButton(hass, entry, subentry)],
                config_subentry_id=subentry_id,
            )


class HoldLatchReleaseButton(HoldLatchEntity, ButtonEntity):
    """Release the latch now. The hold then runs out as normal."""


    def __init__(
        self, hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialise the button."""
        super().__init__(hass, entry, subentry, "release_latch")

    async def async_press(self) -> None:
        """Release the latch."""
        self._engine.async_release_latch()
