"""Config and options flow for Hold & Latch."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    AreaSelector,
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

from .const import (
    CONF_AREA,
    CONF_DEVICE_CLASSES,
    CONF_DOOR_ACTIVE,
    CONF_DOOR_ENTITY,
    CONF_EXCLUDE,
    CONF_HOLD_MODE,
    CONF_HOLD_TIME,
    CONF_HOLD_TYPE,
    CONF_MAX_LATCH,
    CONF_NAME,
    CONF_SOURCE_ENTITY,
    DEFAULT_DEVICE_CLASSES,
    DEFAULT_HOLD_TIME,
    DEFAULT_MAX_LATCH,
    DOMAIN,
    DOOR_ACTIVE_CLOSED,
    DOOR_ACTIVE_OPEN,
    MAX_HOLD_TIME,
    MAX_LATCH_LIMIT,
    MODE_LAST_CLEAR,
    MODE_LAST_DETECTED,
    SUPPORTED_DEVICE_CLASSES,
    TYPE_AREA,
    TYPE_SENSOR,
)

_BINARY_SENSOR = EntitySelectorConfig(domain="binary_sensor")


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


def _source_schema(hold_type: str, opts: dict[str, Any]) -> dict[Any, Any]:
    if hold_type == TYPE_SENSOR:
        return {
            vol.Required(
                CONF_SOURCE_ENTITY, default=opts.get(CONF_SOURCE_ENTITY, vol.UNDEFINED)
            ): EntitySelector(_BINARY_SENSOR),
        }
    return {
        vol.Required(CONF_AREA, default=opts.get(CONF_AREA, vol.UNDEFINED)): AreaSelector(),
        vol.Required(
            CONF_DEVICE_CLASSES,
            default=opts.get(CONF_DEVICE_CLASSES, DEFAULT_DEVICE_CLASSES),
        ): SelectSelector(
            SelectSelectorConfig(
                options=SUPPORTED_DEVICE_CLASSES,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_DEVICE_CLASSES,
            )
        ),
        vol.Optional(
            CONF_EXCLUDE, description={"suggested_value": opts.get(CONF_EXCLUDE, [])}
        ): EntitySelector(EntitySelectorConfig(domain="binary_sensor", multiple=True)),
    }


def _common_schema(opts: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(
            CONF_HOLD_TIME, default=opts.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME)
        ): _seconds(MAX_HOLD_TIME),
        vol.Required(
            CONF_HOLD_MODE, default=opts.get(CONF_HOLD_MODE, MODE_LAST_DETECTED)
        ): SelectSelector(
            SelectSelectorConfig(
                options=[MODE_LAST_DETECTED, MODE_LAST_CLEAR],
                translation_key=CONF_HOLD_MODE,
            )
        ),
        # suggested_value (not default) so the door can be cleared later.
        vol.Optional(
            CONF_DOOR_ENTITY, description={"suggested_value": opts.get(CONF_DOOR_ENTITY)}
        ): EntitySelector(_BINARY_SENSOR),
        vol.Required(
            CONF_DOOR_ACTIVE, default=opts.get(CONF_DOOR_ACTIVE, DOOR_ACTIVE_OPEN)
        ): SelectSelector(
            SelectSelectorConfig(
                options=[DOOR_ACTIVE_OPEN, DOOR_ACTIVE_CLOSED],
                translation_key=CONF_DOOR_ACTIVE,
            )
        ),
        vol.Required(
            CONF_MAX_LATCH, default=opts.get(CONF_MAX_LATCH, DEFAULT_MAX_LATCH)
        ): _seconds(MAX_LATCH_LIMIT),
    }


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise numbers and drop empty optionals."""
    cleaned = dict(user_input)
    for key in (CONF_HOLD_TIME, CONF_MAX_LATCH):
        if key in cleaned:
            cleaned[key] = int(cleaned[key])
    if not cleaned.get(CONF_DOOR_ENTITY):
        cleaned.pop(CONF_DOOR_ENTITY, None)
    if not cleaned.get(CONF_EXCLUDE):
        cleaned.pop(CONF_EXCLUDE, None)
    return cleaned


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    door = user_input.get(CONF_DOOR_ENTITY)
    if door and door == user_input.get(CONF_SOURCE_ENTITY):
        errors[CONF_DOOR_ENTITY] = "door_is_source"
    return errors


class HoldLatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a sensor hold or an area hold."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the hold type."""
        return self.async_show_menu(step_id="user", menu_options=[TYPE_SENSOR, TYPE_AREA])

    async def async_step_sensor_hold(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Hold a single sensor."""
        return await self._async_step_hold(TYPE_SENSOR, user_input)

    async def async_step_area_hold(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Hold a whole area."""
        return await self._async_step_hold(TYPE_AREA, user_input)

    async def _async_step_hold(
        self, hold_type: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                options = _clean(user_input)
                title = options.pop(CONF_NAME)
                return self.async_create_entry(
                    title=title, data={CONF_HOLD_TYPE: hold_type}, options=options
                )

        opts = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=opts.get(CONF_NAME, vol.UNDEFINED)): TextSelector(),
                **_source_schema(hold_type, opts),
                **_common_schema(opts),
            }
        )
        return self.async_show_form(step_id=hold_type, data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return HoldLatchOptionsFlow()


class HoldLatchOptionsFlow(OptionsFlow):
    """Edit an existing hold."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit options."""
        hold_type = self.config_entry.data[CONF_HOLD_TYPE]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(data=_clean(user_input))

        opts = user_input or dict(self.config_entry.options)
        schema = vol.Schema({**_source_schema(hold_type, opts), **_common_schema(opts)})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
