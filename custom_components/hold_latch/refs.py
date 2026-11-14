"""Entity references that survive renames.

Holds store entity *registry IDs* (stable UUIDs) instead of entity IDs, so
renaming a sensor or door doesn't break the hold. Entities that aren't in
the registry (e.g. some YAML entities) are stored by entity ID as before.
"""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def to_ref(hass: HomeAssistant, entity_id: str) -> str:
    """Entity ID -> registry ID, if the entity is registered."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry.id if entry else entity_id


def to_refs(hass: HomeAssistant, entity_ids: Iterable[str]) -> list[str]:
    """Entity IDs -> registry IDs."""
    return [to_ref(hass, entity_id) for entity_id in entity_ids]


def resolve(hass: HomeAssistant, ref: str) -> str | None:
    """Registry ID (or entity ID) -> current entity ID; None if it was deleted."""
    return er.async_resolve_entity_id(er.async_get(hass), ref)


def resolve_all(
    hass: HomeAssistant, refs: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Resolve refs. Returns (entity_ids, refs that no longer exist)."""
    found: list[str] = []
    missing: list[str] = []
    for ref in refs:
        if entity_id := resolve(hass, ref):
            found.append(entity_id)
        else:
            missing.append(ref)
    return found, missing
