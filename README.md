# OpenCARWINGS Home Assistant Integration

[![GitHub Release][releases-shield]][releases]

> **Fork note.** This is the [kriskomp](https://github.com/kriskomp/ha_opencarwings) fork of
> [developerfromjokela/ha_opencarwings](https://github.com/developerfromjokela/ha_opencarwings),
> created by developerfromjokela, who is also the author of the OpenCARWINGS server this integration talks to.
> Changes are listed in [CHANGELOG.md](CHANGELOG.md) and in [Releases](https://github.com/kriskomp/ha_opencarwings/releases):
> a release is published automatically when the version in `manifest.json` changes on `main`.
> Install through HACS as a custom repository (category *Integration*).

Nice, lightweight Home Assistant integration that connects to the OpenCARWINGS API to expose your Nissan (or compatible) cars as devices in Home Assistant.

---

## What it supports ✅

Per car the integration currently exposes:

- Sensors
  - Range (A/C on / A/C off)
  - Charge cable plugged in (plugged / unplugged)
  - High-level status (charging / running / ac_on / idle)
  - **Per-car "Last Updated"** (diagnostic, `timestamp`): when the car last sent a data packet (`ev_info.last_updated`, falling back to `last_connection`). Unique id `ha_opencarwings_last_updated_<VIN>`.
  - **Per-car "Data Age"** (diagnostic): minutes since that packet, refreshed every minute. Unique id `ha_opencarwings_data_age_<VIN>`.
  - **Per-car "Data Fresh"** (binary sensor): on while the data is not older than the threshold set in *Configure* (default 30 min). Unique id `ha_opencarwings_data_fresh_<VIN>`.
  - **Per-car "Command Status"** (diagnostic): result of the last command: `waiting`, `success`, `error` or `timeout`; the attribute `last_confirmed_refresh` tells when the car last answered a refresh command. Unique id `ha_opencarwings_command_status_<VIN>`.
  - **Per-car "Last Requested"** (diagnostic): reports the last time the integration requested data from the API (coordinator's last update time). The sensor is created per VIN and has the unique id pattern `ha_opencarwings_last_requested_<VIN>`.
  - A top-level `OpenCARWINGS Cars` sensor listing your cars and VINs
- Device tracker: car GPS (uses `last_location` / `location` returned by the API). The tracker entity is attached to the same car device as the per-car buttons and shares the car VIN as the device identifier; the tracker entity itself keeps a stable `unique_id` of the form `ha_opencarwings_tracker_<VIN>`. The visible name prefers the car's `nickname` if present, otherwise it falls back to `model_name` (for example, "MyCar Tracker").
- Switch: A/C control (on/off) — sends commands to the car via the OpenCARWINGS command endpoint
- Button: **Manual refresh** — a per-integration button is available to force an immediate refresh from the OpenCARWINGS service (unique id: `ha_opencarwings_refresh_<entry_id>`).
- Button: **Per-car "Request refresh"** — each car has a per-vehicle button labeled like `Request data refresh for <nickname|model>` (for example, "Request data refresh for MyCar"). Pressing it sends a "Refresh data" command to OpenCARWINGS (unique id: `ha_opencarwings_car_refresh_<VIN>`).

---

## Is the data really from the car? ✅

OpenCARWINGS keeps the last data the car sent, so reading the API right after a refresh command can return an
old record. Use these to tell the difference:

- `Data Age` / `Data Fresh` / `Last Updated` come from `ev_info.last_updated`, which the server sets only when a
  data packet actually arrives from the car.
- `Command Status` shows `waiting` until the server gets the car's answer, then `success`, `error` or `timeout`.
  After you press any command button (or toggle A/C) the integration follows the command (every 15 s, up to
  8 min), so these entities update without a script.
- The attributes of the `Status` sensor also show `last_connection`, `last_evinfo` and `data_age_minutes`
  (dates as `dd.mm.yyyy HH:MM`, local time).

## Refresh while charging ⚡

*Settings → Devices & services → OpenCARWINGS → Configure* → **Ask the car for data every N minutes while charging**
(off / 5 / 10 / 15 / 30). The OpenCARWINGS REST API cannot set the server-side periodic refresh, so the integration
sends the "Refresh data" command itself, only when all of these hold:

- the last known state of the car is *charging* (plugged in alone does not count),
- no command is pending,
- N minutes passed since the previous command,
- the data is not younger than N/2 minutes (something else, such as an automation, just refreshed it).

Start of a charge is still up to you (for example an automation that presses the refresh button when the wallbox
starts): the integration cannot know that charging began until it has read fresh data once.

---

## History & Recorder ⚠️

The per-car **Last Updated** sensors are marked as diagnostic (they're metadata, not a regularly changing state) and are typically not recorded by Home Assistant's Recorder. If you want to ensure these sensors are excluded from history/recorder, add an exclusion to your `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - "sensor.ha_opencarwings_last_updated_*"
      - "sensor.ha_opencarwings_last_requested_*"
```

This will prevent per-car `Last Updated` sensors from being stored in your database and showing up in history charts.

---

## Entity names & unique IDs 🔎

A few helpful naming/ID patterns to identify entities created by the integration:

- Device tracker name: uses `nickname` when available, otherwise `model_name`. Visible name example: `MyCar Tracker`.
- Tracker unique_id: `ha_opencarwings_tracker_<VIN>`
- Tracker device identifier: `tracker_<VIN>` (the tracker appears as a separate device; the entity unique id above still applies)
- Per-car "Last Updated" sensor: `ha_opencarwings_last_updated_<VIN>`
- Car refresh button label: `Request data refresh for <nickname|model>` (visible name) — unique id: `ha_opencarwings_car_refresh_<VIN>`
- A/C switch: `ha_opencarwings_ac_<VIN>`

These stable IDs are useful when excluding entities from the recorder or when writing automations targeting specific cars.

These entities are created per-VIN and appear as devices in the Integrations UI.

---

## Installation 🔧

Choose one of the options below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][hacs-repo-badge]][hacs-install]

1. HACS (recommended)
   - In HACS: Integrations → three dots → Custom repositories → Add this repository as category "Integration" → Install → Restart Home Assistant
2. Manual
   - Copy the `custom_components/ha_opencarwings` directory into `<config>/custom_components/` on your Home Assistant host
   - Restart Home Assistant
   - Go to Settings → Devices & Services → Add Integration → search for **OpenCARWINGS** and follow the setup flow

---

## Configuration ⚙️

Setup is done via the UI. You will need:

- **Username** and **Password** for your OpenCARWINGS account
- **Scan interval** (polling frequency, default: 15 minutes). The setup and options flows present a friendly select with labeled choices (for example: "1 minute", "15 minutes (default)", "1 hour", "1 day").
- **API base URL** (optional — defaults to the known OpenCARWINGS endpoint)

The integration obtains JWT tokens (access & refresh) during setup and refreshes tokens automatically.

---

## Development & Tests 🧪

- Run tests with: `pytest`
- The repository includes Home Assistant test stubs under `tests/stubs/` to make running unit tests easier.

---

## To-Do list

- [ ] Implement WebSockets client, to receive real-time updates

---

## Thank you 🙏

A big thank you to the OpenCARWINGS project for providing the reverse-engineered API that makes this integration possible: https://github.com/developerfromjokela/opencarwings

<!-- Badges -->
[releases-shield]: https://img.shields.io/github/v/release/kriskomp/ha_opencarwings?style=for-the-badge
[releases]: https://github.com/kriskomp/ha_opencarwings/releases

[hacs-repo-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-install]: https://my.home-assistant.io/redirect/hacs_repository/?owner=kriskomp&repository=ha_opencarwings&category=Integration

---

## Credits

The integration icon is the OpenCARWINGS logo from [developerfromjokela/opencarwings](https://github.com/developerfromjokela/opencarwings) (`docs/public/favicon.svg`, GPL-2.0). OpenCARWINGS is an independent project, not affiliated with Nissan.

## License

GPL-2.0, see [LICENSE](LICENSE) (the same license as the [OpenCARWINGS server](https://github.com/developerfromjokela/opencarwings)).
