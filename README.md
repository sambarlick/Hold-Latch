# Hold & Latch for Home Assistant

![Built with Claude](https://img.shields.io/badge/Built%20with-Claude-D97757?style=for-the-badge&logo=claude&logoColor=white)
[![Marketplace Custom](https://img.shields.io/badge/Marketplace-Custom-orange.svg?style=for-the-badge)](https://www.home-assistant.io/blog/2026/11/04/release-202611/)
[![GitHub Release](https://img.shields.io/github/release/sambarlick/Hold-Latch.svg?style=for-the-badge&color=blue)](https://github.com/sambarlick/Hold-Latch/releases)
[![Maintainer](https://img.shields.io/badge/maintainer-%40sambarlick-blue.svg?style=for-the-badge)](https://github.com/sambarlick)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sambarlick&repository=Hold-Latch&category=integration)

---

Motion sensor occupancy hold and room occupancy latch for Home Assistant. Hold any motion sensor or whole area, with a latch that keeps a room occupied while the door is closed.

The hold works like the IKEA VALLHORN's built-in occupancy hold, for any sensor.

## ✨ Features

* **⏱️ Occupancy hold:** Occupancy stays on for a set time after motion. New motion restarts the hold.
* **🧲 One sensor or a whole room:** Hold a single sensor, or a whole room (an HA area). Room holds pick up every motion and occupancy sensor in the area, including ones you add or move later.
* **🚪 Optional door latch:** One or more doors. Door closed, then new motion: the room stays occupied until the door opens. Sitting still in a closed room won't turn the lights off.
* **🛡️ No false latches:** Leaving and closing the door behind you doesn't latch an empty room. Only motion *after* the door closes counts.
* **🔁 Two hold modes:** Count from the last motion (IKEA VALLHORN style), or from when motion clears (for presence sensors that stay on).
* **🎚️ Live hold time:** A hold time number entity, adjustable from a dashboard without reloading.
* **🌙 Live latch trigger:** Change what starts the latch from a dashboard or an automation, without a reload.
* **🕒 Clears at:** A timestamp sensor showing when occupancy will clear.
* **💾 Survives restarts:** Latches and hold timing are restored after a restart.
* **🏷️ Survives renames:** Rename a motion or door sensor and the hold keeps working.
* **🩺 Repairs and diagnostics:** A notice appears if a sensor or door is deleted, or stays unavailable for 30 minutes. Download diagnostics from the integration page to see why a room is or isn't latched.

## ⚠️ Known Limitations

* **Latching needs a fast source.** Use the quickest-clearing motion entity, e.g. a VALLHORN's **Motion**, not its **Occupancy**. A sensor with a long built-in hold can stay on through the door closing, so no new motion is seen until it clears.
* **Door sensor offline:** No new latches are made while the door sensor is unavailable. An existing latch is kept until the door opens or the maximum latch time is reached.

## 📥 Installation

### Option 1: Marketplace (Recommended)
Home Assistant 2026.11 and later include the Marketplace (formerly HACS).

1.  Click the **Open your Home Assistant instance** button above, or go to **Settings** -> **Marketplace** -> **Add from link** and enter `https://github.com/sambarlick/Hold-Latch`.
2.  Download **Hold & Latch**.
3.  Restart Home Assistant.

Updates appear under **Settings** -> **Updates**. A restart is needed after updating.

On Home Assistant 2026.10 or earlier, add this repository as a custom repository in HACS (category: **Integration**) instead.

### Option 2: Manual
1.  Download the latest release zip.
2.  Extract the `hold_latch` folder.
3.  Place it in your `config/custom_components/` directory.
4.  Restart Home Assistant.

## ⚙️ Configuration

1.  Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for **Hold & Latch**.
2.  Choose **One sensor** or **A whole room**.
3.  Pick the sensor or area, and set the hold time and hold mode.
4.  Optionally, tick **Add a door latch** and pick the door on the next screen.

For a room hold, the next screen lists the sensors found in that area so you can leave some out, such as your own template sensors or camera detections.

Leave **Name** blank and the hold is named after its sensor or area, e.g. **Ensuite Hold**, or **Ensuite Latch** with a door latch. You can rename it at any time.

Adding the integration sets up your first hold. To add more, open **Settings** -> **Devices & Services** -> **Hold & Latch** and click **Add hold**. To change a hold, use **Edit hold** in its **⋮** menu.

Each hold gets its own device. Everything lives under the one Hold & Latch integration.

For a single-sensor hold, you can tick **Add to the sensor's device** instead. The hold's entities are then added to the motion sensor's own device, which is also listed under Hold & Latch. They're named **Hold**, **Hold ends**, **Hold time**, **Hold latch** and **Hold latch trigger** so they don't clash with the sensor's entities. The sensor's device name, area and other integrations aren't changed.

### Entities

Each hold's device has:

| Entity | What it does |
|---|---|
| **Occupancy** | The held occupancy. Attributes show `motion`, `latched`, `last_detected` and `sources`, plus `door_open` and `latched_since` when a latch is set. |
| **Latch** | On while the door latch is holding the room occupied. Only on holds with a door latch. |
| **Hold ends** | When occupancy will clear. Unknown when the room is clear, latched, or the time can't be known yet (motion still on in *When motion clears* mode). |
| **Hold time** | The hold time in seconds. Changes apply immediately. |
| **Force occupied** | Keeps the room occupied until you switch it off, e.g. for cleaning or a party. When switched off, the hold runs from then. |
| **Release latch** | Releases the latch now. Only on holds with a door latch. |
| **Latch trigger** | What starts the latch (see below). Changes apply immediately, so an automation can switch it by house mode. Only on holds with a door latch. |

### Hold modes

* **Last motion (IKEA VALLHORN style):** Clears the hold time after the last motion started. Best for PIR sensors.
* **When motion clears:** Clears the hold time after every source turns off. Best for mmWave and other presence sensors.

### Door latch (optional)

Pick one or more door sensors. With several, the room counts as **closed** only when all of them are closed, and **open** when any of them is open.

**Latch the room:**
* **While the doors are closed:** For ensuites, toilets and studies. Stays occupied until a door opens.
* **While any door is open:** For garages and sheds. Stays occupied until they're all closed. Also use this if your door sensor reports the opposite way round.

**What starts the latch:**
* **New motion after the doors move into position (recommended):** Leaving and shutting the door behind you won't latch an empty room.
* **Any motion, including motion still showing:** Latches as soon as the doors move into position if the sensor still shows motion. Can latch an empty room if you leave quickly.
* **The doors alone:** No motion needed. For example, a garage stays occupied while any of its doors is open.
* **Maximum latch time:** Releases a stuck latch, for example if the door opening was missed. Set to 0 to turn it off. The default is 3 hours.

When the latch releases, the hold restarts from that moment.

**Changing the trigger by time or mode:** The **Latch trigger** entity changes it without a reload, so an automation can use a different trigger at different times. For example, *New motion* during the day, so closing the door on an empty room doesn't latch it, and *Any motion* at night, so closing the door on someone who's lying still does. If the doors are already in position when it changes, it latches straight away when the new trigger would have: *Any motion* with motion still showing, or *The doors alone*. Changing the trigger never releases an existing latch.

```yaml
action: select.select_option
target:
  entity_id: select.bedroom_latch_trigger
data:
  option: motion_present  # or new_motion, door_only
```

Only motion and occupancy sensors are offered as sources, and only door, garage door and opening sensors as doors.

## Credits
* **Architect & Maintainer:** @sambarlick
* **Code Generation:** Anthropic Claude (AI)
* **Inspiration:** The IKEA VALLHORN's built-in occupancy hold.
