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
  - High-level status (charging / running / ac_on / idle). `running` is shown only while the car's data is up to date; see ["Driving" that never ends](#driving-that-never-ends-) (attribute `driving_unconfirmed`).
  - **Per-car "Last Updated"** (diagnostic, `timestamp`): when the car last sent a data packet (`ev_info.last_updated`, falling back to `last_connection`). Unique id `ha_opencarwings_last_updated_<VIN>`.
  - **Per-car "Data Age"** (diagnostic): time since that packet as text (`37 min`, `2 h 30 min`), numeric value in the attribute `minutes`, refreshed every minute. Unique id `ha_opencarwings_data_age_<VIN>`.
  - **Per-car "Data Fresh"** (binary sensor): on while the data is not older than the threshold set in *Configure* (default 30 min). Unique id `ha_opencarwings_data_fresh_<VIN>`.
  - **"Push Connection"** (binary sensor, diagnostic): on while the live WebSocket to the server is up; attributes `auth_failed`, `last_error`, `last_message`. One per account, attached to the first car's device. Unique id `ha_opencarwings_push_<VIN of the first car>`.
  - **Per-car "Command Status"** (diagnostic): result of the last command: `waiting`, `success`, `error` or `timeout`; the attribute `last_confirmed_refresh` tells when the car last answered a refresh command. Unique id `ha_opencarwings_command_status_<VIN>`.
- Device tracker: car GPS (uses `last_location` / `location` returned by the API). The tracker entity is attached to the same car device as the per-car buttons and shares the car VIN as the device identifier; the tracker entity itself keeps a stable `unique_id` of the form `ha_opencarwings_tracker_<VIN>`.  The visible name uses the car's `nickname` (for example, "MyCar Tracker"). Parked in the Home zone it is not drawn in the Map panel, see [The map](#the-map).
  - **Optional:** *Configure* → **Show the car on the map (device tracker)**. On by default; when switched off no tracker entity exists and the position is also left out of the `Status` sensor attributes (`raw_car`).
- Switch: **A/C**. It shows the car's real A/C state (`ev_info.ac_status`, pushed over the WebSocket) and sends command 3 (on) or 4 (off). After you flip it, it keeps the position you chose (no flip-flop while the car is still answering) until the car reports its state (A/C alerts 4/5/7 from the server), the command fails (error/timeout or alert 97; you get a notification and the switch returns to the car's state), or 15 minutes pass. If the car sends nothing at all for those 15 minutes, the integration sends one "Refresh data" command. Unavailable only when the car's TCU does not support A/C.
- Number: **A/C Temperature** (config, 16-31 °C, default 21, remembered across restarts), only for cars whose TCU takes a temperature (`ficosa2016`, like the Android app). Used by the next "A/C on". Home Assistant shows it in your unit system (°F for US users); the server is always sent whole degrees Celsius.
- Buttons for car commands (unlock/lock doors, horn, lights, remote start/stop, charge start) exist only for commands the car's TCU reports in `supported_commands`.
- Button: **"Reconnect live updates"** (diagnostic, one per account on the first car's device): drops and reopens the WebSocket. If the connection stays down for 10 minutes, Home Assistant also shows a **Repairs** issue with a *Reconnect* fix; it disappears by itself when the connection is back.
- Button: **Per-car "Request refresh"** — each car has a per-vehicle button labeled like `Request data refresh for <nickname|model>` (for example, "Request data refresh for MyCar"). Pressing it sends a "Refresh data" command to OpenCARWINGS (unique id: `ha_opencarwings_car_refresh_<VIN>`).

---

## Live updates (WebSocket)

By default the integration keeps a WebSocket open (`/ws/notif/`) and the server pushes every change (car packet,
location, command result) as it happens. It uses the same personal API token as REST, so no login or password.
The option *Live updates (WebSocket)* in *Configure* turns it off.

What this means in practice:

- While the socket is up, the *Update interval* only acts as a slow safety poll (30 minutes or your interval, whichever
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

## Checking on a parked car 🅿️

*Configure* → **Check on the parked car every N hours/days** (off / 6 h / 12 h / 1 day / 2 days / 3 days / 1 week /
2 weeks). A car that is parked sends nothing by itself, so after a few days you would not know what happens to it.
With this option the integration sends the "Refresh data" command (it wakes the car's modem) when **all** of these hold:

- the car has been silent (no data packet and no connection) for the whole interval,
- it is neither charging nor driving (those have their own behaviour, see below),
- no command is pending,
- no command of any kind was requested within the last interval.

The last rule protects the 12 V battery: a sleeping car that did not answer (timeout or error) is not woken again
until a full interval has passed, and this also holds across Home Assistant restarts. Every wake-up uses some
battery, so choose a long interval (1 day or more is plenty for most people). The check itself runs every 30 minutes
on data the integration already holds and costs nothing. The OpenCARWINGS server has the same feature (car settings,
*Periodic refresh*) but the API cannot change it, so this option lets you manage it from Home Assistant; using both is
safe because the rule above looks at the last command.

## Unanswered refresh (2 minutes) ⏱️

The server keeps a "Refresh data" command *waiting* until its own timeout (5 minutes in its example settings,
`LEAF_COMMAND_TIMEOUT`, a server setting the integration cannot change). A car whose modem sleeps often answers the
second wake-up at once, so the integration does not wait that long: when a refresh it sent (the *Request data refresh*
button, the charging refresh, the parked-car check) has no answer after **2 minutes**, it sends "Refresh data" **once
more** (the server accepts a new command while one is waiting and replaces it) and then gives up until the next
regular cycle. A refresh that is still waiting after 2 minutes also no longer blocks the next charging/parked-car
refresh. Other commands (A/C, doors) are never repeated or replaced.

## "Driving" that never ends 🚗

The server clears "driving" (`car_running`) only when the car sends a data packet with the ignition off. When the
end-of-trip report is declined on the navigation screen (or never sent), the car stays "driving" on the website, in the
Android app and in Home Assistant, sometimes for days. Nothing in the API says otherwise, so:

- If `car_running` is on but the car's last data packet is older than **20 minutes**, the `Status` sensor shows `idle`
  instead of `running` and has the attribute `driving_unconfirmed: true`. (The `Running` sensor still shows what the
  server says.) The parked-car check above is no longer blocked by such a stale "driving".
- Optional, off by default: *Configure* → **Ask a car that seems to be driving every N minutes** (off / 5 / 10 / 15).
  While the car reports driving, the integration sends "Refresh data" at that interval; the answer has the ignition
  state, so a parked car is corrected on the server too (website and app). It stops as soon as the car says it is
  parked. While the car really drives the 12 V battery is charged, but a parked car's is not, so after **3 unanswered
  questions in a row** it pauses until the car sends data by itself (a restart of Home Assistant resets this counter).

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

The diagnostic sensors (`Last Updated`, `Data Age`) are metadata. If you do not want them in the
database and in history charts, exclude them in `configuration.yaml` (match your own entity ids):

```yaml
recorder:
  exclude:
    entity_globs:
      - "sensor.*_last_updated"
      - "sensor.*_data_age"
```

---

## Entity names & unique IDs 🔎

Entities are created per VIN and are grouped under one device per car. Visible names use the car's `nickname`
(for example `Leaf Data Age`). Stable unique IDs, useful for automations:

| Entity | Unique ID |
| --- | --- |
| Device tracker | `ha_opencarwings_tracker_<VIN>` |
| Status / Last Updated / Data Age / Command Status | `ha_opencarwings_status_<VIN>`, `…_last_updated_<VIN>`, `…_data_age_<VIN>`, `…_command_status_<VIN>` |
| Data Fresh / Push Connection (binary sensors) | `ha_opencarwings_data_fresh_<VIN>`, `ha_opencarwings_push_<VIN>` |
| A/C switch / A/C Temperature | `ha_opencarwings_ac_<VIN>`, `ha_opencarwings_ac_temperature_<VIN>` |
| Reconnect button (once per account) | `ha_opencarwings_reconnect_<entry_id>` |
| Request data refresh button | `ha_opencarwings_car_refresh_<VIN>` |

Door buttons: command 7 (*Unlock Doors*) has the unique id `…_car_doorlock_<VIN>` and command 8 (*Lock Doors*) has
`…_car_doorunlock_<VIN>` (historical, kept). Older versions had the **entity ids** the wrong way round
(`button.*_lock_doors*` sent the unlock command); on startup the integration renames them so the entity id matches the
action (`…unlock_doors…` = command 7, `…lock_doors…` = command 8). Update automations that used the old ids.

`raw_car`, the full car object in the `Status` sensor attributes, is excluded from the recorder (not stored in the database).
The "6.6 kW OBC Exists" and "Battery Heater Exists" sensors are diagnostic.

Charge-time sensors (3 kW, 1 kW, 6.6 kW) and `Data Age` show readable text (`4 h 52 min`); the number of minutes is in
the attribute `minutes`.

---

## TODO (ideas from the Android app, not yet done) 📝

1. PIN for sensitive commands (`command_pin`, `sensitive_commands`, `command_pin_enforced`).
2. Python client: new spec fields (`charging_interrupted`, `power_available`, `lease_contract`).
3. Status like the app (Charging interrupted / Plugged in / Driving / Parked / "Charging, ~3 h 42 min left"; estimate priority OBC 6.6 kW > 240 V > 120 V).
4. Remaining charge-time sensor (treat 4097 as "no estimate").
5. Battery capacity kWh (`max_gids * 80 Wh * SOH`), Navi ID (`tcu_serial`), carrier and signal sensors.
6. Hide cabin temperature for non-TCU033 and align model detection with the app (vehicle_code1 92/146 = AZE0; VIN "VZK" for e-NV200).
7. Vehicle Health (TPMS, DTC, maintenance alert, mileage).
8. Timers, alerts list, TCU configuration (command 5), send-to-car/route plans, distance history.
9. Plug as a binary sensor.

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
  only acts as a backup read (30 minutes or your interval, whichever is longer), see [Live updates](#live-updates-websocket).
- **API address** (optional, defaults to `https://opencarwings.viaaq.eu`): change it if you run your own server.

*Settings → Devices & services → OpenCARWINGS → Configure* has all of the above plus:

| Option | Default | What it does |
| --- | --- | --- |
| Live updates (WebSocket) | on | Server pushes changes; turn off if your network blocks WebSockets. |
| Check on the parked car every N hours/days | off | Asks a silent, parked car for data, see *Checking on a parked car* below. |
| Ask a car that seems to be driving every N minutes | off | Asks a car that reports driving until it says it is parked, see ["Driving" that never ends](#driving-that-never-ends-). |
| Ask the car for data every N minutes while charging | off | Sends "Refresh data" while the car charges, see [Refresh while charging](#refresh-while-charging-). |
| Data counts as fresh for (minutes) | 30 | Threshold of the `Data Fresh` binary sensor. |
| Show the car on the map (device tracker) | on | Off: no tracker entity, and no position in the `Status` attributes. |

Changing an option reloads the integration. If the server rejects the token, Home Assistant asks for a new one
(re-authentication) instead of failing silently.

### Events

The service `ha_opencarwings.refresh`, the account-level *OpenCARWINGS Refresh* button, the *Last Requested* and *OpenCARWINGS Cars*
sensors and the nameless account device were removed (they only re-read the server, which the WebSocket already does). Stale entities are removed
automatically. To ask the car for data use the per-car *Request data refresh* button.

- Event `ha_opencarwings_alert`: fired for `alert` messages pushed by the server (needs the WebSocket).

### Example Lovelace card

Similar to the Android app (replace the entity ids with yours):

```yaml
type: vertical-stack
cards:
  - type: horizontal-stack
    cards:
      - {type: button, entity: button.leaf_unlock_doors, icon: mdi:lock-open-variant, name: Unlock, show_state: false}
      - {type: button, entity: button.leaf_lock_doors, icon: mdi:lock, name: Lock, show_state: false}
      - {type: button, entity: button.leaf_charge_start, icon: mdi:flash, name: Charge, show_state: false}
      - {type: button, entity: switch.leaf_a_c, name: A/C, show_state: false}
      - {type: button, entity: button.leaf_horn_lights, icon: mdi:car-light-alert, name: Lights, show_state: false}
  - type: entities
    entities:
      - number.leaf_a_c_temperature
      - sensor.leaf_range
      - sensor.leaf_battery
```

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
