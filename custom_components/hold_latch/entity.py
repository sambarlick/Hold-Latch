"""Base entity for Hold & Latch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .refs import resolve
from .const import CONF_ATTACH, CONF_HOLD_TYPE, CONF_SOURCE_ENTITY, DOMAIN, TYPE_SENSOR


def attached_device_id(hass: HomeAssistant, subentry: ConfigSubentry) -> str | None:
    """Device the hold should show on, if it's attached to its sensor's device."""
    data = subentry.data
    if data.get(CONF_HOLD_TYPE) != TYPE_SENSOR or not data.get(CONF_ATTACH):
        return None
    entity_id = resolve(hass, data[CONF_SOURCE_ENTITY])
    device = async_entity_id_to_device(hass, entity_id) if entity_id else None
    return device.id if device else None


if TYPE_CHECKING:
    from . import HoldLatchConfigEntry


class HoldLatchEntity(Entity):
    """Common behaviour: one device per hold, push updates from its engine."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    # Name used when the entity sits on the sensor's own device, so it doesn't
    # clash with the sensor's entities (e.g. "Hold" next to "Occupancy").
    _attached_translation_key: str | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HoldLatchConfigEntry,
        subentry: ConfigSubentry,
        key: str,
    ) -> None:
        """Initialise the entity."""
        self._entry = entry
        self._subentry_id = subentry.subentry_id
        self._engine = entry.runtime_data.engines[subentry.subentry_id]
        self._attr_unique_id = f"{subentry.subentry_id}_{key}"
        self._attr_translation_key = key

        if (device_id := attached_device_id(hass, subentry)) and (
            device := dr.async_get(hass).async_get(device_id)
        ):
            # Share the sensor's device: it's listed under Hold & Latch too, but
            # its name, area and other integrations are left as they are.
            self._attr_device_info = DeviceInfo(
                identifiers=device.identifiers, connections=device.connections
            )
            self._attr_translation_key = self._attached_translation_key or key
            return

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Hold & Latch",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to engine updates."""
        self.async_on_remove(self._engine.async_add_listener(self.async_write_ha_state))
