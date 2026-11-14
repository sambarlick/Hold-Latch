"""Hold and latch engine for Hold & Latch.

Rules
-----
* Any source on                      -> occupied.
* All sources off                    -> occupied until ``clears_at``:
    - last_detected mode: last motion onset + hold
    - last_clear mode:    moment all sources cleared + hold
* Door configured, door closed, and a *new* motion onset (off -> on) after
  the door closed -> latched: occupied until the door opens.
* Door opens while latched           -> unlatch; the hold restarts from now.
* Latched longer than max latch      -> unlatch (escape hatch; 0 disables).
* Door unavailable/unknown           -> no new latches, existing latch kept.
* Source returning from unavailable  -> counts for the hold, never latches.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DOOR_ACTIVE_OPEN, MODE_LAST_DETECTED, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

_UNKNOWN_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


class HoldEngine:
    """Tracks source sensors and an optional door, and decides occupancy."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        hold_seconds: int,
        hold_mode: str,
        door_entity: str | None,
        door_active: str,
        max_latch_seconds: int,
    ) -> None:
        """Initialise the engine."""
        self.hass = hass
        self._hold = timedelta(seconds=hold_seconds)
        self._hold_mode = hold_mode
        self._door_entity = door_entity
        self._door_active = door_active
        self._max_latch = (
            timedelta(seconds=max_latch_seconds) if max_latch_seconds else None
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )

        self._sources: set[str] = set()
        self._active: set[str] = set()
        self._door_open: bool | None = None  # None = no door, or door unknown

        self.occupied = False
        self.latched = False
        self.latched_since: datetime | None = None
        self.last_detected: datetime | None = None
        self.last_clear: datetime | None = None
        self.door_closed_at: datetime | None = None
        self._released_at: datetime | None = None

        self._unsub_sources: CALLBACK_TYPE | None = None
        self._unsub_door: CALLBACK_TYPE | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ props

    @property
    def hold_seconds(self) -> int:
        """Current hold time in seconds."""
        return int(self._hold.total_seconds())

    @property
    def sources(self) -> set[str]:
        """Entity IDs currently feeding this hold."""
        return set(self._sources)

    @property
    def any_source_on(self) -> bool:
        """True while any source sensor is on."""
        return bool(self._active)

    @property
    def door_configured(self) -> bool:
        """True if a door entity is configured."""
        return self._door_entity is not None

    @property
    def door_open(self) -> bool | None:
        """Door open state; None if no door or door state unknown."""
        return self._door_open

    @property
    def clears_at(self) -> datetime | None:
        """When occupancy will clear, or None while held open-ended."""
        if self.latched or self.any_source_on:
            return None
        reference = self._reference()
        return reference + self._hold if reference else None

    # -------------------------------------------------------------- lifecycle

    async def async_load(self) -> None:
        """Restore persisted state."""
        data = await self._store.async_load() or {}
        self.occupied = bool(data.get("occupied", False))
        self.latched = bool(data.get("latched", False))
        self.latched_since = _from_iso(data.get("latched_since"))
        self.last_detected = _from_iso(data.get("last_detected"))
        self.last_clear = _from_iso(data.get("last_clear"))
        self._released_at = _from_iso(data.get("released_at"))
        if self.latched and not self.door_configured:
            # Door was removed from the config; a latch can't be released.
            self.latched = False
            self.latched_since = None
        if self.latched and self.latched_since is None:
            self.latched_since = dt_util.utcnow()

    @callback
    def async_start(self) -> None:
        """Start tracking the door. Sources are set via async_set_sources."""
        now = dt_util.utcnow()
        if self._door_entity:
            self._door_open = self._door_state(self.hass.states.get(self._door_entity))
            if self._door_open is False:
                # Already closed: only motion from now on can latch.
                self.door_closed_at = now
            elif self._door_open is True and self.latched:
                self._unlatch(now)
            self._unsub_door = async_track_state_change_event(
                self.hass, [self._door_entity], self._handle_door
            )
        self._evaluate(now)

    @callback
    def async_stop(self) -> None:
        """Stop all tracking and flush state."""
        for unsub in (self._unsub_sources, self._unsub_door, self._unsub_timer):
            if unsub:
                unsub()
        self._unsub_sources = self._unsub_door = self._unsub_timer = None
        self._listeners.clear()
        self._store.async_delay_save(self._data_to_save, 0)

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a callback for state changes."""
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    # ------------------------------------------------------------- configure

    @callback
    def async_set_sources(self, entity_ids: set[str]) -> None:
        """Replace the set of source sensors."""
        entity_ids = set(entity_ids)
        if self._door_entity:
            entity_ids.discard(self._door_entity)
        if entity_ids == self._sources and (self._unsub_sources or not entity_ids):
            return

        if self._unsub_sources:
            self._unsub_sources()
            self._unsub_sources = None

        self._sources = entity_ids
        self._active = {
            entity_id
            for entity_id in entity_ids
            if (state := self.hass.states.get(entity_id)) and state.state == STATE_ON
        }
        if entity_ids:
            self._unsub_sources = async_track_state_change_event(
                self.hass, list(entity_ids), self._handle_source
            )
        _LOGGER.debug("Sources now %s", sorted(entity_ids))
        self._evaluate(dt_util.utcnow())

    @callback
    def async_set_hold(self, seconds: int) -> None:
        """Change the hold time live."""
        self._hold = timedelta(seconds=seconds)
        self._evaluate(dt_util.utcnow())

    # ---------------------------------------------------------------- events

    @callback
    def _handle_source(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        now = dt_util.utcnow()

        was_any_on = self.any_source_on
        was_on = old_state is not None and old_state.state == STATE_ON
        is_on = new_state is not None and new_state.state == STATE_ON

        if is_on:
            self._active.add(entity_id)
        else:
            self._active.discard(entity_id)

        if is_on and not was_on:
            self.last_detected = now
            # Only a genuine off -> on is new motion. Coming back from
            # unavailable/unknown (restart, reconnect) never latches.
            genuine_onset = old_state is not None and old_state.state == STATE_OFF
            if genuine_onset and self._door_open is False:
                self._latch(now)

        if was_any_on and not self.any_source_on:
            self.last_clear = now

        self._evaluate(now)

    @callback
    def _handle_door(self, event: Event[EventStateChangedData]) -> None:
        now = dt_util.utcnow()
        previous = self._door_open
        self._door_open = self._door_state(event.data["new_state"])

        if self._door_open is False and previous is not False:
            self.door_closed_at = now
        elif self._door_open is True:
            self.door_closed_at = None
            if self.latched:
                self._unlatch(now)
        elif self._door_open is None:
            # Door went unavailable: block new latches, keep an existing one.
            self.door_closed_at = None

        self._evaluate(now)

    @callback
    def _handle_timer(self, now: datetime) -> None:
        self._unsub_timer = None
        self._evaluate(dt_util.utcnow())

    # --------------------------------------------------------------- helpers

    def _door_state(self, state: State | None) -> bool | None:
        """Return True if open, False if closed, None if unknown."""
        if state is None or state.state in _UNKNOWN_STATES:
            return None
        is_on = state.state == STATE_ON
        return is_on if self._door_active == DOOR_ACTIVE_OPEN else not is_on

    def _reference(self) -> datetime | None:
        """Moment the hold counts from."""
        reference = (
            self.last_detected
            if self._hold_mode == MODE_LAST_DETECTED
            else self.last_clear
        )
        if self._released_at and (reference is None or self._released_at > reference):
            reference = self._released_at
        return reference

    def _latch(self, now: datetime) -> None:
        if not self.latched:
            _LOGGER.debug("Latched")
            self.latched = True
            self.latched_since = now

    def _unlatch(self, now: datetime) -> None:
        if self.latched:
            _LOGGER.debug("Unlatched")
        self.latched = False
        self.latched_since = None
        self._released_at = now

    @callback
    def _evaluate(self, now: datetime) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

        if (
            self.latched
            and self._max_latch
            and self.latched_since
            and now >= self.latched_since + self._max_latch
        ):
            _LOGGER.debug("Max latch reached")
            self._unlatch(now)

        deadline: datetime | None = None
        if self.latched:
            occupied = True
            if self._max_latch and self.latched_since:
                deadline = self.latched_since + self._max_latch
        elif self.any_source_on:
            occupied = True
        else:
            clears_at = self.clears_at
            occupied = clears_at is not None and now < clears_at
            if occupied:
                deadline = clears_at

        if deadline:
            self._unsub_timer = async_track_point_in_utc_time(
                self.hass, self._handle_timer, deadline
            )

        self.occupied = occupied
        self._store.async_delay_save(self._data_to_save, 1)
        for listener in list(self._listeners):
            listener()

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "occupied": self.occupied,
            "latched": self.latched,
            "latched_since": _to_iso(self.latched_since),
            "last_detected": _to_iso(self.last_detected),
            "last_clear": _to_iso(self.last_clear),
            "released_at": _to_iso(self._released_at),
        }
