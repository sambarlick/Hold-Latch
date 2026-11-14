"""Live hold-time control for Hold & Latch."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HoldLatchConfigEntry
from .const import CONF_HOLD_TIME, MAX_HOLD_TIME
from .entity import HoldLatchEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HoldLatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the hold time number."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry_id in entry.runtime_data.engines:
            async_add_entities(
                [HoldLatchTimeNumber(hass, entry, subentry)],
                config_subentry_id=subentry_id,
            )


class HoldLatchTimeNumber(HoldLatchEntity, NumberEntity):
    """Hold time, adjustable without reloading.

    Writes to the hold's subentry data, so reconfiguring the hold and this
    entity always agree; the update listener applies it live.
    """

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_HOLD_TIME
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(
        self, hass: HomeAssistant, entry: HoldLatchConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialise the number."""
        super().__init__(hass, entry, subentry, "hold_time")

    @property
    def native_value(self) -> float:
        """Return the hold time."""
        return self._engine.hold_seconds

    async def async_set_native_value(self, value: float) -> None:
        """Set the hold time."""
        subentry = self._entry.subentries[self._subentry_id]
        self.hass.config_entries.async_update_subentry(
            self._entry,
            subentry,
            data={**subentry.data, CONF_HOLD_TIME: int(value)},
        )
