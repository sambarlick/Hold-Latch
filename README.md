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
* **🧲 Sensor or area:** Hold a single sensor, or a whole area. Area holds pick up every motion and occupancy sensor in the area, including ones you add or move later.
* **🚪 Door latch:** Door closed, then new motion: the room stays occupied until the door opens. Sitting still in a closed room won't turn the lights off.
* **🛡️ No false latches:** Leaving and closing the door behind you doesn't latch an empty room. Only motion *after* the door closes counts.
* **🔁 Two hold modes:** Count from the last motion (VALLHORN-style), or from when motion clears (for presence sensors that stay on).
* **🎚️ Live hold time:** A hold time number entity, adjustable from a dashboard without reloading.
* **🕒 Clears at:** A timestamp sensor showing when occupancy will clear.
* **💾 Survives restarts:** Latches and hold timing are restored after a restart.

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
2.  Choose **Hold a single sensor** or **Hold a whole area**.
3.  Set the hold time and hold mode.
4.  Optionally, add a door sensor to enable the latch.

To change a hold later, go to **Settings** -> **Devices & Services** -> **Hold & Latch** and click the **settings cog**.

### Entities

Each hold creates a device with:

| Entity | What it does |
|---|---|
| **Occupancy** | The held occupancy. Attributes show `motion`, `latched`, `last_detected` and `sources`, plus `door_open` and `latched_since` when a door is set. |
| **Clears at** | When occupancy will clear. Unknown while motion is on or the room is latched. |
| **Hold time** | The hold time in seconds. Changes apply immediately. |

### Hold modes

* **Last motion (VALLHORN-style):** Clears the hold time after the last motion started. Best for PIR sensors.
* **When motion clears:** Clears the hold time after every source turns off. Best for mmWave and other presence sensors.

### Door latch

* **Door sensor 'on' means:** Most door sensors report on = open. Pick **Closed (inverted)** if yours reports on = closed.
* **Maximum latch time:** Releases a stuck latch, for example if the door opening was missed. Set to 0 to disable. The default is 3 hours.

When the door opens, the latch releases and the hold restarts from that moment.

## Credits
* **Architect & Maintainer:** @sambarlick
* **Code Generation:** Anthropic Claude (AI)
* **Inspiration:** The IKEA VALLHORN's built-in occupancy hold.
