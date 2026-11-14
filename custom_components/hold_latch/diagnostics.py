"""Diagnostics for Hold & Latch."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import HoldLatchConfigEntry, _holds
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HoldLatchConfigEntry
) -> dict[str, Any]:
    """Each hold's settings, live state and the states it's reading."""
    runtime = entry.runtime_data
    issues = ir.async_get(hass).issues
    holds: dict[str, Any] = {}
    for subentry_id, subentry in _holds(entry).items():
        engine = runtime.engines.get(subentry_id)
        snapshot = engine.snapshot() if engine else {}
        watched = sorted(
            set(snapshot.get("sources", [])) | set(snapshot.get("doors", {}))
        )
        holds[subentry.title] = {
            "subentry_id": subentry_id,
            "settings": dict(subentry.data),
            "state": snapshot,
            "entity_states": {
                entity_id: (
                    state.state if (state := hass.states.get(entity_id)) else None
                )
                for entity_id in watched
            },
            "repairs": sorted(
                issue_id
                for domain, issue_id in issues
                if domain == DOMAIN and issue_id.startswith(f"{subentry_id}_")
            ),
        }
    return {"holds": holds}
