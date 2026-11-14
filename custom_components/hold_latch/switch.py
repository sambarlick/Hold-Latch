"""Force-occupied switch for Hold & Latch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Add a Force occupied switch to every hold."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id in entry.runtime_data.engines:
            async_add_entities(
                [HoldLatchForceSwitch(hass, entry, subentry)],
                config_subentry_id=subentry_id,
            )


class HoldLatchForceSwitch(HoldLatchEntity, SwitchEntity):
    """Keep the room occupied until switched off (e.g. cleaning, a party).

    Remembered across restarts. Switching off starts the hold from then.
    """

    _attached_translation_key = "force_hold_on"

    def __init__(
        self, hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialise the switch."""
        super().__init__(hass, entry, subentry, "force_occupied")

    @property
    def is_on(self) -> bool:
        """Return True while forced."""
        return self._engine.forced

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Force occupied."""
        self._engine.async_set_forced(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop forcing; the hold runs from now."""
        self._engine.async_set_forced(False)
