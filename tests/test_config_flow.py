"""Config and options flow tests."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hold_latch.const import DOMAIN


async def test_sensor_hold_flow_and_options(hass: HomeAssistant):
    """Create a sensor hold, then edit it."""
    hass.states.async_set("binary_sensor.wardrobe_motion", "off")
    hass.states.async_set("binary_sensor.ensuite_door", "on")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "sensor_hold"}
    )
    assert result["type"] is FlowResultType.FORM

    # Door == source is rejected.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Ensuite",
            "source_entity": "binary_sensor.wardrobe_motion",
            "door_entity": "binary_sensor.wardrobe_motion",
            "hold_time": 90,
            "hold_mode": "last_detected",
            "door_active": "open",
            "max_latch": 10800,
        },
    )
    assert result["errors"] == {"door_entity": "door_is_source"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Ensuite",
            "source_entity": "binary_sensor.wardrobe_motion",
            "door_entity": "binary_sensor.ensuite_door",
            "hold_time": 90.0,
            "hold_mode": "last_detected",
            "door_active": "open",
            "max_latch": 10800.0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "Ensuite"
    assert entry.options["hold_time"] == 90
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ensuite_occupancy") is not None

    # Options: remove the door -> reload, latch attributes disappear.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "source_entity": "binary_sensor.wardrobe_motion",
            "hold_time": 60,
            "hold_mode": "last_clear",
            "door_active": "open",
            "max_latch": 0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "door_entity" not in entry.options
    assert "door_open" not in hass.states.get("binary_sensor.ensuite_occupancy").attributes
    assert hass.states.get("number.ensuite_hold_time").state == "60"


async def test_area_hold_flow(hass: HomeAssistant):
    """Create an area hold."""
    from homeassistant.helpers import area_registry as ar

    area = ar.async_get(hass).async_create("Back Hallway")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "area_hold"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Back Hallway",
            "area": area.id,
            "device_classes": ["motion", "occupancy"],
            "hold_time": 120,
            "hold_mode": "last_detected",
            "door_active": "open",
            "max_latch": 0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].options["area"] == area.id
