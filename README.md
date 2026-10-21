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
  - **Per-car "Data Age"** (diagnostic): time since that packet as text (`37 min`, `2 h 30 min`), numeric value in the attribute `minutes`, refreshed every minute. Unique id `ha_opencarwings_data_age_<VIN>`.
  - **Per-car "Data Fresh"** (binary sensor): on while the data is not older than the threshold set in *Configure* (default 30 min). Unique id `ha_opencarwings_data_fresh_<VIN>`.
  - **Per-car "Push Connection"** (binary sensor, diagnostic): on while the live WebSocket to the server is up; attributes `auth_failed`, `last_error`, `last_message`. Unique id `ha_opencarwings_push_<VIN>`.
  - **Per-car "Command Status"** (diagnostic): result of the last command: `waiting`, `success`, `error` or `timeout`; the attribute `last_confirmed_refresh` tells when the car last answered a refresh command. Unique id `ha_opencarwings_command_status_<VIN>`.
  - **Per-car "Last Requested"** (diagnostic): a native `timestamp`: the last time the integration read data from the API (shown by HA as "x minutes ago"). The sensor is created per VIN and has the unique id pattern `ha_opencarwings_last_requested_<VIN>`.
  - A top-level `OpenCARWINGS Cars` sensor listing your cars and VINs
- Device tracker: car GPS (uses `last_location` / `location` returned by the API). The tracker entity is attached to the same car device as the per-car buttons and shares the car VIN as the device identifier; the tracker entity itself keeps a stable `unique_id` of the form `ha_opencarwings_tracker_<VIN>`.  The visible name uses the car's `nickname` (for example, "MyCar Tracker"). Parked in the Home zone it is not drawn in the Map panel, see [The map](#the-map).
  - **Optional:** *Configure* → **Show the car on the map (device tracker)**. On by default; when switched off no tracker entity exists and the position is also left out of the `Status` sensor attributes (`raw_car`).
- Switch: A/C control (on/off) — sends commands to the car via the OpenCARWINGS command endpoint. It is unavailable only when the car's TCU does not support A/C commands; the switch does not show the real A/C state (the API has none), it only sends the command.
- Button: **Manual refresh** — a per-integration button is available to force an immediate refresh from the OpenCARWINGS service (unique id: `ha_opencarwings_refresh_<entry_id>`).
- Buttons for car commands (unlock/lock doors, horn, lights, remote start/stop, charge start) exist only for commands the car's TCU reports in `supported_commands`.
- Button: **Per-car "Request refresh"** — each car has a per-vehicle button labeled like `Request data refresh for <nickname|model>` (for example, "Request data refresh for MyCar"). Pressing it sends a "Refresh data" command to OpenCARWINGS (unique id: `ha_opencarwings_car_refresh_<VIN>`).

---

## Live updates (WebSocket)

By default the integration keeps a WebSocket open (`/ws/notif/`) and the server pushes every change (car packet,
location, command result) as it happens. It uses the same personal API token as REST, so no login or password.
The option *Live updates (WebSocket)* in *Configure* turns it off.

What this means in practice:

- While the socket is up, the *Update interval* only acts as a slow safety poll (1 hour or your interval, whichever
  is longer); when it drops, polling returns to your normal interval.
- The server does not replay missed events, so after **every** (re)connect the whole state is re-read over REST.
- Dead connections are detected with a 30 s WebSocket heartbeat; reconnects wait 5 s, doubling up to 5 min.
- If the server rejects the token, the integration stops retrying fast, retries hourly and asks for a new token
  (re-authentication, no need to delete the integration).
- A WebSocket cannot make the car send new data: *Refresh data* (button, or *Ask the car for data every N minutes
  while charging*) is still needed. What changes is that the result arrives immediately instead of being polled
  (command follow-up polls 4x less often while the socket is up).
- Server `alert` messages are fired as the event `ha_opencarwings_alert`.

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

The diagnostic sensors (`Last Updated`, `Last Requested`, `Data Age`) are metadata. If you do not want them in the
database and in history charts, exclude them in `configuration.yaml` (match your own entity ids):

```yaml
recorder:
  exclude:
    entity_globs:
      - "sensor.*_last_updated"
      - "sensor.*_last_requested"
      - "sensor.*_data_age"
```

---

## Entity names & unique IDs 🔎

Entities are created per VIN and are grouped under one device per car. Visible names use the car's `nickname`
(for example `Leaf Data Age`). Stable unique IDs, useful for automations:

| Entity | Unique ID |
| --- | --- |
| Device tracker | `ha_opencarwings_tracker_<VIN>` |
| Status / Last Updated / Data Age / Command Status / Last Requested | `ha_opencarwings_status_<VIN>`, `…_last_updated_<VIN>`, `…_data_age_<VIN>`, `…_command_status_<VIN>`, `…_last_requested_<VIN>` |
| Data Fresh / Push Connection (binary sensors) | `ha_opencarwings_data_fresh_<VIN>`, `ha_opencarwings_push_<VIN>` |
| A/C switch | `ha_opencarwings_ac_<VIN>` |
| Request data refresh button | `ha_opencarwings_car_refresh_<VIN>` |

Door buttons: command 7 (*Unlock Doors*) has the id `…_car_doorlock_<VIN>` and command 8 (*Lock Doors*) has
`…_car_doorunlock_<VIN>`. The ids are historical and kept stable so existing entities do not change.

Charge-time sensors (3 kW, 1 kW, 6.6 kW) and `Data Age` show readable text (`4 h 52 min`); the number of minutes is in
the attribute `minutes`.

---

## Installation 🔧

Choose one of the options below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][hacs-repo-badge]][hacs-install]

1. HACS (recommended)
   - In HACS: Integrations → three dots → Custom repositories → Add this repository as category "Integration" → Install → Restart Home Assistant, then add the integration as described under *Configuration* below
2. Manual
   - Copy the `custom_components/ha_opencarwings` directory into `<config>/custom_components/` on your Home Assistant host
   - Restart Home Assistant
   - Go to Settings → Devices & Services → Add Integration → search for **OpenCARWINGS** and follow the setup flow

---

## Configuration ⚙️

Setup is done in the UI (*Settings → Devices & services → Add integration → OpenCARWINGS*). You need:

- **API token**: the **API-key** shown on your account page on the OpenCARWINGS website (paste it as the token). No username or password is
  used; the same token is used for REST and for the WebSocket.
- **Update interval** (default 15 minutes): how often the server is read over REST. While the live WebSocket is up it
  only acts as a slow safety poll, see [Live updates](#live-updates-websocket).
- **API address** (optional, defaults to `https://opencarwings.viaaq.eu`): change it if you run your own server.

*Settings → Devices & services → OpenCARWINGS → Configure* has all of the above plus:

| Option | Default | What it does |
| --- | --- | --- |
| Live updates (WebSocket) | on | Server pushes changes; turn off if your network blocks WebSockets. |
| Ask the car for data every N minutes while charging | off | Sends "Refresh data" while the car charges, see [Refresh while charging](#refresh-while-charging-). |
| Data counts as fresh for (minutes) | 30 | Threshold of the `Data Fresh` binary sensor. |
| Show the car on the map (device tracker) | on | Off: no tracker entity, and no position in the `Status` attributes. |

Changing an option reloads the integration. If the server rejects the token, Home Assistant asks for a new one
(re-authentication) instead of failing silently.

### Services and events

- Service `ha_opencarwings.refresh` (optional `entry_id`): reads the server now (it does not ask the car for data; use the
  *Request data refresh* button for that).
- Event `ha_opencarwings_alert`: fired for `alert` messages pushed by the server (needs the WebSocket).

### The map

Home Assistant's **Map** panel does not show entities whose state is `home`, so a car parked in the *Home* zone is not
drawn there (your phones behave the same way). While driving (`not_home`) it appears. To see it always, add a map card:

```yaml
type: map
entities:
  - entity: device_tracker.<your_car>_tracker
    label_mode: icon
```

---

## Development & Tests 🧪

- Run tests with: `pytest`
- The repository includes Home Assistant test stubs under `tests/stubs/` to make running unit tests easier.

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
