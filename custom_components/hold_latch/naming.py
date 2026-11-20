"""Automatic hold names for Hold & Latch."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device import async_entity_id_to_device

from .const import CONF_AREA, CONF_HOLD_TYPE, TYPE_SENSOR, door_entities


def _suffix(data: dict[str, Any]) -> str:
    return "Latch" if door_entities(data) else "Hold"


def _sensor_name(hass: HomeAssistant, entity_id: str) -> str:
    """The sensor's device name, else its own name, else its entity ID."""
    if (device := async_entity_id_to_device(hass, entity_id)) and (
        name := device.name_by_user or device.name
    ):
        return name
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _area_name(
    hass: HomeAssistant, data: dict[str, Any], source: str | None
) -> str | None:
    """The hold's area: its own for a room hold, else its sensor's."""
    area_reg = ar.async_get(hass)
    if data[CONF_HOLD_TYPE] != TYPE_SENSOR:
        area_id = data.get(CONF_AREA)
    elif source:
        entity = er.async_get(hass).async_get(source)
        device = async_entity_id_to_device(hass, source)
        area_id = (entity.area_id if entity else None) or (
            device.area_id if device else None
        )
    else:
        area_id = None
    area = area_reg.async_get_area(area_id) if area_id else None
    return area.name if area else None


def _base(hass: HomeAssistant, data: dict[str, Any], source: str | None) -> str:
    """Area name, else (sensor holds) the sensor's name."""
    if area := _area_name(hass, data, source):
        return area
    return _sensor_name(hass, source) if source else "Room"


def auto_name(hass: HomeAssistant, data: dict[str, Any], source: str | None) -> str:
    """'<area> Hold', or '<area> Latch' with a door latch.

    A sensor hold without an area uses the sensor's name. source is the
    resolved entity ID of a sensor hold's sensor.
    """
    return f"{_base(hass, data, source)} {_suffix(data)}"


def old_auto_names(
    hass: HomeAssistant, data: dict[str, Any], source: str | None
) -> set[str]:
    """Names earlier versions gave a hold whose name was left blank.

    v0.8 and older: '<sensor> Hold/Latch' (room holds: '<area> Hold/Latch').
    v0.9: the area alone, or the sensor's name.
    """
    names = {_base(hass, data, source)}
    if data[CONF_HOLD_TYPE] == TYPE_SENSOR and source:
        names.add(f"{_sensor_name(hass, source)} {_suffix(data)}")
    return names
