"""Live latch-trigger control for Hold & Latch."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HoldLatchConfigEntry
from .const import CONF_LATCH_TRIGGER, LATCH_TRIGGERS
from .entity import HoldLatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HoldLatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a Latch trigger select to holds with a door latch."""
    for subentry_id, subentry in entry.subentries.items():
        engine = entry.runtime_data.engines.get(subentry_id)
        if engine and engine.door_configured:
            async_add_entities(
                [HoldLatchTriggerSelect(hass, entry, subentry)],
                config_subentry_id=subentry_id,
            )


class HoldLatchTriggerSelect(HoldLatchEntity, SelectEntity):
    """What starts the latch, changeable without reloading.

    Lets an automation switch it by house mode, e.g. Motion present at night
    (a still sleeper behind a closed door) and New motion by day (no false
    latch when you leave and shut the door). Writes to the hold's subentry
    data, so reconfiguring the hold and this entity always agree; the update
    listener applies it live.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = LATCH_TRIGGERS

    def __init__(
        self, hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialise the select."""
        super().__init__(hass, entry, subentry, "latch_trigger")

    @property
    def current_option(self) -> str:
        """Return the current latch trigger."""
        return self._engine.latch_trigger

    async def async_select_option(self, option: str) -> None:
        """Set the latch trigger."""
        subentry = self._entry.subentries[self._subentry_id]
        self.hass.config_entries.async_update_subentry(
            self._entry,
            subentry,
            data={**subentry.data, CONF_LATCH_TRIGGER: option},
        )
