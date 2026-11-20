"""Config flow for Hold & Latch.

Adding the integration walks straight into creating the first hold. Each
hold is a config subentry: more are added with "Add hold" on the
integration page, and each can be reconfigured from its ⋮ menu.

Steps, shared by both flows:
  user (menu)  -> sensor_hold | area_hold  -> latch (only if "Add a door latch")
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.selector import (
    AreaSelector,
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .area import discover_area_sources
from .naming import auto_name
from .refs import resolve, resolve_all, to_ref, to_refs
from .const import (
    CONF_ADD_LATCH,
    CONF_AREA,
    CONF_ATTACH,
    CONF_DEVICE_CLASSES,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_EXCLUDE,
    CONF_HOLD_MODE,
    CONF_HOLD_TIME,
    CONF_HOLD_TYPE,
    CONF_LATCH_TRIGGER,
    CONF_LATCH_WHEN,
    CONF_MAX_LATCH,
    CONF_NAME,
    CONF_SOURCE_ENTITY,
    DEFAULT_DEVICE_CLASSES,
    DEFAULT_HOLD_TIME,
    DEFAULT_MAX_LATCH,
    DOMAIN,
    DOOR_DEVICE_CLASSES,
    LATCH_WHEN_CLOSED,
    LATCH_WHEN_OPEN,
    MAX_HOLD_TIME,
    MAX_LATCH_LIMIT,
    MODE_LAST_CLEAR,
    MODE_LAST_DETECTED,
    SOURCE_DEVICE_CLASSES,
    SUBENTRY_HOLD,
    SUPPORTED_DEVICE_CLASSES,
    TYPE_AREA,
    TRIGGER_DOOR_ONLY,
    TRIGGER_MOTION_PRESENT,
    TRIGGER_NEW_MOTION,
    TYPE_SENSOR,
    door_entities,
)

_LATCH_KEYS = (
    CONF_DOOR_ENTITY,
    CONF_DOOR_ENTITIES,
    CONF_LATCH_WHEN,
    CONF_LATCH_TRIGGER,
    CONF_MAX_LATCH,
)


def _seconds(maximum: int) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=maximum,
            step=1,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    )


def _default(data: dict[str, Any], key: str, fallback: Any = vol.UNDEFINED) -> Any:
    return data.get(key, fallback)


def _hold_schema(hold_type: str, data: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {
        # Optional: left blank, it becomes "<sensor or area> Hold" or "... Latch".
        vol.Optional(
            CONF_NAME, description={"suggested_value": data.get(CONF_NAME)}
        ): TextSelector(),
    }
    if hold_type == TYPE_SENSOR:
        fields[
            vol.Required(CONF_SOURCE_ENTITY, default=_default(data, CONF_SOURCE_ENTITY))
        ] = EntitySelector(
            EntitySelectorConfig(
                domain="binary_sensor", device_class=SOURCE_DEVICE_CLASSES
            )
        )
    else:
        fields[vol.Required(CONF_AREA, default=_default(data, CONF_AREA))] = (
            AreaSelector()
        )
        fields[
            vol.Required(
                CONF_DEVICE_CLASSES,
                default=_default(data, CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=SUPPORTED_DEVICE_CLASSES,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_DEVICE_CLASSES,
            )
        )

    fields[
        vol.Required(
            CONF_HOLD_TIME, default=_default(data, CONF_HOLD_TIME, DEFAULT_HOLD_TIME)
        )
    ] = _seconds(MAX_HOLD_TIME)
    fields[
        vol.Required(
            CONF_HOLD_MODE, default=_default(data, CONF_HOLD_MODE, MODE_LAST_DETECTED)
        )
    ] = SelectSelector(
        SelectSelectorConfig(
            options=[MODE_LAST_DETECTED, MODE_LAST_CLEAR],
            translation_key=CONF_HOLD_MODE,
        )
    )
    fields[vol.Required(CONF_ADD_LATCH, default=bool(door_entities(data)))] = (
        BooleanSelector()
    )
    return vol.Schema(fields)


def _latch_schema(data: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DOOR_ENTITIES, default=door_entities(data) or vol.UNDEFINED
            ): EntitySelector(
                EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class=DOOR_DEVICE_CLASSES,
                    multiple=True,
                )
            ),
            vol.Required(
                CONF_LATCH_WHEN,
                default=_default(data, CONF_LATCH_WHEN, LATCH_WHEN_CLOSED),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[LATCH_WHEN_CLOSED, LATCH_WHEN_OPEN],
                    translation_key=CONF_LATCH_WHEN,
                )
            ),
            vol.Required(
                CONF_LATCH_TRIGGER,
                default=_default(data, CONF_LATCH_TRIGGER, TRIGGER_NEW_MOTION),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        TRIGGER_NEW_MOTION,
                        TRIGGER_MOTION_PRESENT,
                        TRIGGER_DOOR_ONLY,
                    ],
                    translation_key=CONF_LATCH_TRIGGER,
                )
            ),
            vol.Required(
                CONF_MAX_LATCH,
                default=_default(data, CONF_MAX_LATCH, DEFAULT_MAX_LATCH),
            ): _seconds(MAX_LATCH_LIMIT),
        }
    )


class _HoldSteps:
    """Hold setup steps shared by the config flow and the subentry flow."""

    _data: dict[str, Any]
    _add_latch: bool = False

    def _init_data(self, data: dict[str, Any] | None = None) -> None:
        if not hasattr(self, "_data"):
            self._data = dict(data or {})

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Choose what to hold."""
        self._init_data()
        return self.async_show_menu(
            step_id="user", menu_options=[TYPE_SENSOR, TYPE_AREA]
        )

    async def async_step_sensor_hold(self, user_input: dict[str, Any] | None = None):
        """Hold one sensor."""
        return await self._async_hold_step(TYPE_SENSOR, user_input)

    async def async_step_area_hold(self, user_input: dict[str, Any] | None = None):
        """Hold a whole area."""
        return await self._async_hold_step(TYPE_AREA, user_input)

    async def _async_hold_step(self, hold_type: str, user_input: dict[str, Any] | None):
        self._init_data()
        if user_input is not None:
            add_latch = user_input.pop(CONF_ADD_LATCH, False)
            # Switching type on reconfigure must not leave the old type's keys.
            # (CONF_ATTACH: removed in v0.9, dropped from older holds here.)
            for key in (
                CONF_NAME,
                CONF_ATTACH,
                CONF_SOURCE_ENTITY,
                CONF_AREA,
                CONF_DEVICE_CLASSES,
            ):
                self._data.pop(key, None)
            self._data.update(user_input)
            self._data[CONF_HOLD_TYPE] = hold_type
            self._data[CONF_HOLD_TIME] = int(self._data[CONF_HOLD_TIME])
            self._add_latch = add_latch
            if hold_type == TYPE_AREA:
                return await self.async_step_area_exclude()
            return await self._async_after_hold()

        return self.async_show_form(
            step_id=hold_type, data_schema=_hold_schema(hold_type, self._data)
        )

    async def async_step_area_exclude(self, user_input: dict[str, Any] | None = None):
        """Pick sensors to leave out, from the ones found in the area."""
        found = sorted(
            discover_area_sources(
                self.hass,  # type: ignore[attr-defined]
                self._data[CONF_AREA],
                self._data.get(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES),
                [],
                [],
            )
        )
        if user_input is not None or not found:
            exclude = [
                e for e in (user_input or {}).get(CONF_EXCLUDE, []) if e in found
            ]
            if exclude:
                self._data[CONF_EXCLUDE] = exclude
            else:
                self._data.pop(CONF_EXCLUDE, None)
            return await self._async_after_hold()

        previous = [e for e in self._data.get(CONF_EXCLUDE, []) if e in found]
        area = ar.async_get(self.hass).async_get_area(self._data[CONF_AREA])  # type: ignore[attr-defined]
        return self.async_show_form(
            step_id="area_exclude",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_EXCLUDE, description={"suggested_value": previous}
                    ): EntitySelector(
                        EntitySelectorConfig(include_entities=found, multiple=True)
                    )
                }
            ),
            description_placeholders={
                "count": str(len(found)),
                "area": area.name if area else "",
            },
        )

    async def _async_after_hold(self):
        if self._add_latch:
            return await self.async_step_latch()
        for key in _LATCH_KEYS:
            self._data.pop(key, None)
        return self._async_finish()

    async def async_step_latch(self, user_input: dict[str, Any] | None = None):
        """Configure the door latch."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_DOOR_ENTITIES):
                errors[CONF_DOOR_ENTITIES] = "no_doors"
            elif self._data.get(CONF_SOURCE_ENTITY) in user_input[CONF_DOOR_ENTITIES]:
                errors[CONF_DOOR_ENTITIES] = "door_is_source"
            else:
                self._data.pop(CONF_DOOR_ENTITY, None)  # old single-door key
                self._data.update(user_input)
                self._data[CONF_MAX_LATCH] = int(self._data[CONF_MAX_LATCH])
                return self._async_finish()

        return self.async_show_form(
            step_id="latch",
            data_schema=_latch_schema(user_input or self._data),
            errors=errors,
        )

    def _split(self) -> tuple[str, dict[str, Any]]:
        """Title and data to save, with entities stored by registry ID."""
        hass = self.hass  # type: ignore[attr-defined]
        data = dict(self._data)
        name = (data.pop(CONF_NAME, None) or "").strip() or self._auto_name(data)
        if source := data.get(CONF_SOURCE_ENTITY):
            data[CONF_SOURCE_ENTITY] = to_ref(hass, source)
        for key in (CONF_DOOR_ENTITIES, CONF_EXCLUDE):
            if data.get(key):
                data[key] = to_refs(hass, data[key])
        return name, data

    def _auto_name(self, data: dict[str, Any]) -> str:
        """'<area> Hold', or '<area> Latch' with a door latch."""
        return auto_name(
            self.hass,  # type: ignore[attr-defined]
            data,
            data.get(CONF_SOURCE_ENTITY) if data[CONF_HOLD_TYPE] == TYPE_SENSOR else None,
        )

    def _async_finish(self):
        raise NotImplementedError


class HoldLatchConfigFlow(_HoldSteps, ConfigFlow, domain=DOMAIN):
    """Add Hold & Latch, starting with its first hold."""

    VERSION = 1
    MINOR_VERSION = 2

    def _async_finish(self) -> ConfigFlowResult:
        title, data = self._split()
        return self.async_create_entry(
            title="Hold & Latch",
            data={},
            subentries=[
                {
                    "subentry_type": SUBENTRY_HOLD,
                    "title": title,
                    "data": data,
                    "unique_id": None,
                }
            ],
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Holds are subentries."""
        return {SUBENTRY_HOLD: HoldSubentryFlow}


class HoldSubentryFlow(_HoldSteps, ConfigSubentryFlow):
    """Add or reconfigure a hold."""

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit an existing hold. Its type can't change: go straight to its form."""
        subentry = self._get_reconfigure_subentry()
        data = {**subentry.data, CONF_NAME: subentry.title}
        # Stored by registry ID; the form works with current entity IDs.
        if source := data.get(CONF_SOURCE_ENTITY):
            data[CONF_SOURCE_ENTITY] = resolve(self.hass, source) or source
        if doors := door_entities(data):
            data.pop(CONF_DOOR_ENTITY, None)
            data[CONF_DOOR_ENTITIES] = resolve_all(self.hass, doors)[0]
        if exclude := data.get(CONF_EXCLUDE):
            data[CONF_EXCLUDE] = resolve_all(self.hass, exclude)[0]
        self._init_data(data)
        if self._data[CONF_HOLD_TYPE] == TYPE_SENSOR:
            return await self.async_step_sensor_hold()
        return await self.async_step_area_hold()

    def _async_finish(self) -> SubentryFlowResult:
        title, data = self._split()
        if self.source == "reconfigure":
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=data,
            )
        return self.async_create_entry(title=title, data=data)
