"""Live hold-time control for Hold & Latch."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
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
    async_add_entities([HoldLatchTimeNumber(entry)])


class HoldLatchTimeNumber(HoldLatchEntity, NumberEntity):
    """Hold time, adjustable without reloading.

    Writes to the entry's options, so the options flow and this entity
    always agree; the update listener applies it live.
    """

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_HOLD_TIME
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, entry: HoldLatchConfigEntry) -> None:
        """Initialise the number."""
        super().__init__(entry, "hold_time")

    @property
    def native_value(self) -> float:
        """Return the hold time."""
        return self._engine.hold_seconds

    async def async_set_native_value(self, value: float) -> None:
        """Set the hold time."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_HOLD_TIME: int(value)},
        )
