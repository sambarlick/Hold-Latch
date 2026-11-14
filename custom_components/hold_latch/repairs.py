"""Repairs notices for Hold & Latch.

* A configured sensor or door was deleted -> raised at once.
* A configured sensor or door stays unavailable -> raised after a while,
  and cleared as soon as it comes back.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import DOMAIN

UNAVAILABLE_AFTER = timedelta(minutes=30)


def _unavailable(state: State | None) -> bool:
    return state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)


@callback
def async_clear_hold_issues(hass: HomeAssistant, subentry_id: str) -> None:
    """Remove every notice for one hold."""
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and issue_id.startswith(f"{subentry_id}_"):
            ir.async_delete_issue(hass, DOMAIN, issue_id)


@callback
def async_raise_missing(
    hass: HomeAssistant, subentry_id: str, hold: str, role: str, ref: str
) -> None:
    """A configured sensor or door no longer exists."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{subentry_id}_missing_{ref}",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=f"missing_{role}",
        translation_placeholders={"hold": hold},
    )


class AvailabilityWatcher:
    """Raise a notice when a sensor or door stays unavailable."""

    def __init__(
        self,
        hass: HomeAssistant,
        subentry_id: str,
        hold: str,
        entities: dict[str, str],
        delay: timedelta = UNAVAILABLE_AFTER,
    ) -> None:
        """entities: entity_id -> role ("sensor" or "door")."""
        self.hass = hass
        self._subentry_id = subentry_id
        self._hold = hold
        self._entities = entities
        self._delay = delay
        self._timers: dict[str, CALLBACK_TYPE] = {}
        self._unsub: CALLBACK_TYPE | None = None

    def _issue_id(self, entity_id: str) -> str:
        return f"{self._subentry_id}_unavailable_{entity_id}"

    @callback
    def async_start(self) -> None:
        """Start watching."""
        if not self._entities:
            return
        for entity_id in self._entities:
            self._check(entity_id, self.hass.states.get(entity_id))
        self._unsub = async_track_state_change_event(
            self.hass, list(self._entities), self._handle
        )

    @callback
    def async_stop(self) -> None:
        """Stop watching. Leaves raised notices in place."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    @callback
    def _handle(self, event: Event[EventStateChangedData]) -> None:
        self._check(event.data["entity_id"], event.data["new_state"])

    @callback
    def _check(self, entity_id: str, state: State | None) -> None:
        if not _unavailable(state):
            if cancel := self._timers.pop(entity_id, None):
                cancel()
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(entity_id))
            return
        if entity_id in self._timers:
            return

        @callback
        def _raise(_now) -> None:
            self._timers.pop(entity_id, None)
            role = self._entities[entity_id]
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id(entity_id),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=f"unavailable_{role}",
                translation_placeholders={"hold": self._hold, "entity": entity_id},
            )

        self._timers[entity_id] = async_call_later(self.hass, self._delay, _raise)
