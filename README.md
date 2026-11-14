# Hold & Latch

Motion sensor occupancy hold and room occupancy latch for Home Assistant. Hold any motion sensor or whole area, with a latch that keeps a room occupied while the door is closed.

The hold works like the IKEA VALLHORN's built-in occupancy hold, for any sensor.

## What it creates

For each hold, a device with:

| Entity | What it does |
|---|---|
| `binary_sensor.<name>_occupancy` | The held occupancy |
| `sensor.<name>_clears_at` | When the hold clears (a timestamp; unknown while motion is on or latched) |
| `number.<name>_hold_time` | Hold time, adjustable live without a reload |

Attributes on the occupancy sensor: `motion`, `latched`, `last_detected`, `sources`, plus `door_open` and `latched_since` when a door is set.

## Hold types

- **Sensor hold:** one source sensor.
- **Area hold:** every `binary_sensor` in an HA area (assigned directly or via its device) whose device class is selected. The defaults are motion and occupancy. New or moved sensors are picked up automatically.

## Hold modes

- **Last motion (VALLHORN-style):** occupancy clears *hold time* after the last motion onset. Good for PIRs.
- **When motion clears:** occupancy clears *hold time* after every source turns off. Use this for presence sensors that stay on.

## Door latch

Set a door sensor to enable it:

- Door closed, then **new** motion (off → on) → **latched**: occupied until the door opens.
- Door opens → unlatched, and the hold restarts from that moment.
- Leaving and closing the door behind you doesn't latch, because there's no new motion after the close.
- Door unavailable → no new latches; an existing latch is kept.
- A source returning from unavailable (restart, reconnect) never latches.
- **Maximum latch time** releases a stuck latch (0 disables).
- **Door sensor 'on' means:** *Open* (standard) or *Closed* (inverted contact).

**Tip:** for latching, use the fastest-clearing entity as the source, e.g. a VALLHORN's **Motion**, not its **Occupancy**. A sensor with a long built-in hold can stay on through the door closing, so no new onset is seen until it clears.

## Install

Copy `custom_components/hold_latch` into your HA config, or add this repo to HACS as a custom repository. Restart, then go to *Settings → Devices & services → Add integration → Hold & Latch*.

State (latch, last motion) persists across restarts.
