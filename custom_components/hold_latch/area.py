"""Area source discovery for Hold & Latch."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN


def discover_area_sources(
    hass: HomeAssistant,
    area_id: str,
    device_classes: list[str],
    exclude: list[str],
    door_entity: str | None,
) -> set[str]:
    """Return binary sensors in an area matching the device classes.

    An entity is in the area if it's assigned directly, or if it has no area
    of its own and its device is in the area (HA's normal inheritance).
    This integration's own entities are always skipped, to avoid feedback.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    skip = set(exclude)
    if door_entity:
        skip.add(door_entity)

    found: set[str] = set()
    for entry in ent_reg.entities.values():
        if (
            entry.domain != "binary_sensor"
            or entry.platform == DOMAIN
            or entry.disabled_by is not None
            or entry.entity_id in skip
        ):
            continue

        entity_area = entry.area_id
        if entity_area is None and entry.device_id:
            device = dev_reg.async_get(entry.device_id)
            entity_area = device.area_id if device else None
        if entity_area != area_id:
            continue

        device_class = entry.device_class or entry.original_device_class
        if device_class in device_classes:
            found.add(entry.entity_id)
    return found
