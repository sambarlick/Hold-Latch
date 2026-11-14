"""Config and subentry flow tests."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar

from custom_components.hold_latch.const import DOMAIN, SUBENTRY_HOLD

HOLD = {
    "name": "Ensuite",
    "source_entity": "binary_sensor.ensuite_motion",
    "hold_time": 90.0,
    "hold_mode": "last_detected",
}


async def _first_hold(hass, add_latch: bool):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["sensor_hold", "area_hold"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "sensor_hold"}
    )
    assert result["step_id"] == "sensor_hold"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {**HOLD, "add_latch": add_latch}
    )


async def test_onboarding_without_latch(hass: HomeAssistant):
    """Adding the integration creates it with its first hold. No latch screen."""
    hass.states.async_set(
        "binary_sensor.ensuite_motion", "off", {"device_class": "motion"}
    )
    result = await _first_hold(hass, add_latch=False)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "Hold & Latch"
    (sub,) = entry.subentries.values()
    assert sub.title == "Ensuite"
    assert sub.data["hold_time"] == 90
    assert "door_entity" not in sub.data
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ensuite_occupancy") is not None


async def test_onboarding_with_latch(hass: HomeAssistant):
    """Ticking 'Add a door latch' adds the latch screen."""
    hass.states.async_set(
        "binary_sensor.ensuite_motion", "off", {"device_class": "motion"}
    )
    hass.states.async_set("binary_sensor.ensuite_door", "on", {"device_class": "door"})
    result = await _first_hold(hass, add_latch=True)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "latch"

    # The motion sensor can't be the door.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "door_entity": "binary_sensor.ensuite_motion",
            "latch_when": "closed",
            "max_latch": 10800,
        },
    )
    assert result["errors"] == {"door_entity": "door_is_source"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "door_entity": "binary_sensor.ensuite_door",
            "latch_when": "closed",
            "max_latch": 10800.0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    (sub,) = result["result"].subentries.values()
    assert sub.data["door_entity"] == "binary_sensor.ensuite_door"
    assert sub.data["latch_when"] == "closed"
    assert sub.data["max_latch"] == 10800


async def test_single_instance(hass: HomeAssistant):
    """A second 'Add integration' is refused; holds are added inside it."""
    hass.states.async_set("binary_sensor.ensuite_motion", "off")
    await _first_hold(hass, add_latch=False)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_add_area_hold_and_reconfigure(hass: HomeAssistant):
    """'Add hold' adds a room hold; reconfigure edits it and removes the latch."""
    hass.states.async_set("binary_sensor.ensuite_motion", "off")
    hass.states.async_set("binary_sensor.hall_door", "on", {"device_class": "door"})
    entry = (await _first_hold(hass, add_latch=False))["result"]
    await hass.async_block_till_done()
    area = ar.async_get(hass).async_create("Back Hallway")

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_HOLD), context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "area_hold"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Back Hallway",
            "area": area.id,
            "device_classes": ["motion", "occupancy"],
            "hold_time": 120,
            "hold_mode": "last_detected",
            "add_latch": True,
        },
    )
    assert result["step_id"] == "latch"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "door_entity": "binary_sensor.hall_door",
            "latch_when": "open",
            "max_latch": 0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(entry.subentries) == 2
    assert hass.states.get("binary_sensor.back_hallway_occupancy") is not None

    hall = next(s for s in entry.subentries.values() if s.title == "Back Hallway")
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_HOLD),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": hall.subentry_id,
        },
    )
    # Type can't change: straight to the room form, prefilled.
    assert result["step_id"] == "area_hold"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Back Hall",
            "area": area.id,
            "device_classes": ["motion"],
            "hold_time": 60,
            "hold_mode": "last_clear",
            "add_latch": False,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    hall = entry.subentries[hall.subentry_id]
    assert hall.title == "Back Hall"
    assert hall.data["hold_time"] == 60
    assert "door_entity" not in hall.data
    assert (
        "door_open"
        not in hass.states.get("binary_sensor.back_hallway_occupancy").attributes
    )
