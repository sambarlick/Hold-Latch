"""Hold and latch engine for Hold & Latch.

Rules
-----
* Any source on                      -> occupied.
* All sources off                    -> occupied until ``clears_at``:
    - last_detected mode: last motion onset + hold
    - last_clear mode:    moment all sources cleared + hold
* Door configured and in its latch position (closed by default), and a
  *new* motion onset (off -> on) after it got there -> latched: occupied
  until the door leaves that position.
* Door leaves the latch position     -> unlatch; the hold restarts from now.
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

from .const import DOMAIN, LATCH_WHEN_CLOSED, MODE_LAST_DETECTED, STORAGE_VERSION

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
        storage_id: str,
        hold_seconds: int,
        hold_mode: str,
        door_entity: str | None,
        latch_when: str,
        max_latch_seconds: int,
    ) -> None:
        """Initialise the engine."""
        self.hass = hass
        self._hold = timedelta(seconds=hold_seconds)
        self._hold_mode = hold_mode
        self._door_entity = door_entity
        self._latch_when = latch_when
        self._max_latch = (
            timedelta(seconds=max_latch_seconds) if max_latch_seconds else None
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{storage_id}"
        )

        self._sources: set[str] = set()
        self._active: set[str] = set()
        self._door_open: bool | None = None  # None = no door, or door unknown

        self.occupied = False
        self.latched = False
        self.latched_since: datetime | None = None
        self.last_detected: datetime | None = None
        self.last_clear: datetime | None = None
        self.door_closed_at: datetime | None = (
            None  # when it reached the latch position
        )
        self._released_at: datetime | None = None

        self._unsub_sources: CALLBACK_TYPE | None = None
        self._unsub_door: CALLBACK_TYPE | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []
        self._stopped = False

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
    def _door_in_latch_position(self) -> bool | None:
        """True if the door is where it holds the latch; None if unknown."""
        if self._door_open is None:
            return None
        if self._latch_when == LATCH_WHEN_CLOSED:
            return not self._door_open
        return self._door_open

    @property
    def clears_at(self) -> datetime | None:
        """When occupancy will clear, or None while it can't be known.

        None while latched. While motion is still on, it's only known in
        last-motion mode (the hold already runs from the onset), and only until
        that time passes with motion still on.
        """
        if self.latched:
            return None
        reference = self._reference()
        if reference is None:
            return None
        clears_at = reference + self._hold
        if self.any_source_on:
            if self._hold_mode != MODE_LAST_DETECTED or clears_at <= dt_util.utcnow():
                return None
        return clears_at

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
            in_position = self._door_in_latch_position
            if in_position is True:
                # Already in position: only motion from now on can latch.
                self.door_closed_at = now
            elif in_position is False and self.latched:
                self._unlatch(now)
            self._unsub_door = async_track_state_change_event(
                self.hass, [self._door_entity], self._handle_door
            )
        self._evaluate(now)

    @callback
    def async_stop(self, *, save: bool = True) -> None:
        """Stop all tracking and flush state. Safe to call twice."""
        if self._stopped:
            return
        self._stopped = True
        for unsub in (self._unsub_sources, self._unsub_door, self._unsub_timer):
            if unsub:
                unsub()
        self._unsub_sources = self._unsub_door = self._unsub_timer = None
        self._listeners.clear()
        if save:
            self._store.async_delay_save(self._data_to_save, 0)

    async def async_remove_storage(self) -> None:
        """Stop without saving and delete the saved state (hold deleted)."""
        self.async_stop(save=False)
        await self._store.async_remove()

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
            if genuine_onset and self._door_in_latch_position is True:
                self._latch(now)

        if was_any_on and not self.any_source_on:
            self.last_clear = now

        self._evaluate(now)

    @callback
    def _handle_door(self, event: Event[EventStateChangedData]) -> None:
        now = dt_util.utcnow()
        previous = self._door_in_latch_position
        self._door_open = self._door_state(event.data["new_state"])
        in_position = self._door_in_latch_position

        if in_position is True and previous is not True:
            self.door_closed_at = now
        elif in_position is False:
            self.door_closed_at = None
            if self.latched:
                self._unlatch(now)
        elif in_position is None:
            # Door went unavailable: block new latches, keep an existing one.
            self.door_closed_at = None

        self._evaluate(now)

    @callback
    def _handle_timer(self, now: datetime) -> None:
        self._unsub_timer = None
        self._evaluate(dt_util.utcnow())

    # --------------------------------------------------------------- helpers

    def _door_state(self, state: State | None) -> bool | None:
        """Return True if open, False if closed, None if unknown (on = open)."""
        if state is None or state.state in _UNKNOWN_STATES:
            return None
        return state.state == STATE_ON

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
            # Re-check when the predicted clear time passes with motion still on.
            deadline = self.clears_at
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
        if not self._stopped:
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
