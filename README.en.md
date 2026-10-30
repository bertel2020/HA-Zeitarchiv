<p align="center">
  <img src="https://raw.githubusercontent.com/bertel2020/HA-Zeitarchiv/main/custom_components/zeitarchiv/brand/logo.png" alt="Zeitarchiv" width="160">
</p>

<h1 align="center">Zeitarchiv Integration</h1>

<p align="center">
  The reliable write path from Home Assistant into Zeitarchiv.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <a href="https://github.com/bertel2020/HA-Zeitarchiv/releases"><img src="https://img.shields.io/github/v/release/bertel2020/HA-Zeitarchiv?sort=semver" alt="Release"></a>
  <a href="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/validate.yml"><img src="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/tests.yml"><img src="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/bertel2020/HA-Zeitarchiv" alt="License"></a>
</p>

<p align="center">
  <a href="https://buymeacoffee.com/bertel2020"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-FFDD00?logo=buy-me-a-coffee&logoColor=black" alt="Buy Me a Coffee"></a>
  <a href="https://ko-fi.com/bertel2020"><img src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
  <a href="https://paypal.me/RobertoMartins"><img src="https://img.shields.io/badge/PayPal-donate-00457C?logo=paypal&logoColor=white" alt="PayPal"></a>
</p>

<p align="center"><em><a href="README.md">Deutsche Version</a></em></p>

The Zeitarchiv integration watches selected state changes and transmits them
in batches to the [Zeitarchiv app](https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv). It
does not create copies of the archived entities in Home Assistant: the actual
time series, charts and tables remain the app's job.

## What the integration does

| Task | Behavior |
| --- | --- |
| **Entity selection** | Labels preferred; optionally combine individual entities, areas, devices and entity patterns |
| **Exclusions** | Individual entity IDs and exclusion patterns always take precedence |
| **Value processing** | Numeric values with configurable decimal places (0–3, default 3), plus switch (`on`/`off`) and presence (`home`/`not_home`) states |
| **Reliable transport** | In-memory queue, batches, timeout and persistent retries |
| **Secure connection** | Bearer token; reauth prompt when the token is rejected |
| **Diagnostics** | Four diagnostic sensors and a diagnostics download |
| **Transferring filters** | Export/import as versioned YAML — handy for applying the same selection to a second system |

## Installation

### Via HACS (recommended)

[![Open the HACS repository in My Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bertel2020&repository=HA-Zeitarchiv&category=integration)
[![Add Zeitarchiv to My Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zeitarchiv)

1. Use the first button to open the Zeitarchiv repository in HACS.
2. Download **Zeitarchiv** and restart Home Assistant.
3. Use the second button to add the integration. Alternatively, open **Settings
   → Devices & services → Add integration → Zeitarchiv** in Home Assistant.

If the first button does not work, add
`https://github.com/bertel2020/HA-Zeitarchiv` in HACS under **Integrations →
Custom repositories** with the category **Integration**.

### Manual

#### 1. Prerequisite

The [Zeitarchiv app](https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv) must be running. You
can find the API token there under **Settings → Connection**.

App and integration are versioned independently; no particular minimum
version is required — newer features (e.g. the operating mode sensor) are
simply left unused against an older counterpart instead of disrupting the
connection.

#### 2. Copy the custom integration

Copy the `custom_components/zeitarchiv` directory to
`/config/custom_components/zeitarchiv` and restart Home Assistant.

#### 3. Set up the connection

In Home Assistant, open **Settings → Devices & services → Add integration →
Zeitarchiv** and enter:

| Field | Meaning |
| --- | --- |
| Connection name | Freely chosen name, e.g. `Production` or `Test` |
| Host | Reachable host of the Zeitarchiv app |
| Port | `8127` by default |
| API token | Token from the app settings |

The connection is tested before saving. An unreachable host and a rejected
token appear as separate error messages.

Multiple connections can be set up in parallel. Each connection has its own
queue, its own filters and its own diagnostic sensors. This allows the same
Home Assistant to send its state changes to a production and a test
Zeitarchiv at the same time, for example; two named entries with identical
host and port are also allowed. Only a second entry with the same host, port
**and** token is rejected, because it would send every value twice to the
same app.

#### 4. Choose archive filters

On the Zeitarchiv integration tile, open **Configure → Edit archive
filters**.

| Selection | Effect |
| --- | --- |
| Labels (recommended) | Directly labelled entities as well as entities of labelled devices and areas; changes apply to subsequent state changes without saving again |
| Individual entities | Additional specific entity IDs |
| Areas | All entities currently assigned |
| Devices | All entities currently assigned |
| Excluded entities | Always discarded |
| Include entity patterns | `*`/`?` patterns; without a dot for object IDs, with a dot for full entity IDs |
| Exclude entity patterns | Pattern-based exclusions with the same precedence as individual exclusions |
| Decimal places | Rounding of numeric values before transmission, 0–3, default 3 |

After submitting, a review step shows the entity IDs that were actually
resolved. The preview distinguishes active entities, registered entities
without a current state, and entities removed by exclusions. For labels,
areas and devices this makes all associated entities visible before the
selection is saved. The preview also states the configured decimal places;
switch states are stored as `1/0` regardless.

Via **Configure → Currently included entities** the same report can be opened
at any later time for the saved filters, without changing the selection.

Domain filters are no longer offered. On upgrade, previously saved domain
selections are converted once into the concrete entity IDs known at that
time. For new entities and those added later, labels are the preferred way.

## Data flow

```text
Integration loaded/reloaded ─► current state
state_changed               ───► new state change
     │
     ├─ actual state change only?
     ├─ filter matches and not excluded?
     └─ supported value?
             │
             ▼
       In-memory queue
       max. 5,000 events
             │
             ▼
       Batch of up to 100 events
       or after 5 s at the latest
             │
             ▼
       Zeitarchiv app :8127
```

A stable event ID makes repeated transmissions idempotent. If an HTTP
response is lost, the same batch can be sent again without the app creating
the same data point twice.

Immediately when an integration entry is loaded or reloaded, the current
states of all matching entities are queued once. Newly selected entities
therefore appear in the app right away; the integration waits neither for the
next state change nor for a restart of Home Assistant.

## Which values are archived?

The integration only reacts when the actual state changes. A mere change of
attributes such as friendly name or unit does not create an additional
archive point.

- Numeric states of `sensor`, `climate`, `input_number`, `counter` and
  comparable domains are transmitted as numbers with the decimal places set in
  the options flow (0–3, default 3). The default is recommended; fewer decimal
  places improve the compressibility of the app's long-term storage and can
  noticeably save space with very many entities and long retention, but cost
  precision for fine-grained measurements (e.g. current in A).
- `binary_sensor`, `switch`, `input_boolean`, `light`, `fan`, `automation`,
  `script`, `remote`, `siren`, `humidifier`, `update` and `calendar` are
  transmitted as `on → 1` and `off → 0`.
- `device_tracker` and `person` are transmitted as presence: `home → 1`, any
  other state (`not_home` or a named zone other than `home`) `→ 0`.
- Text values (e.g. `Heating`/`Idle` of a thermostat or a washing machine's
  programme) are transmitted as a state, with the translation from Home
  Assistant where one exists. This only applies to **individually selected**
  entities: text sensors deliberately do not come along via a pattern or a
  selection by area, device or label. For such entities `unknown` and
  `unavailable` are sent to the app as well, which records them as
  "unavailable".
- If the connected app cannot accept states yet (older version), text values
  are not archived. So this does not go unnoticed, the integration then
  reports individually selected entities with text values as a repair card
  and in the log (see
  [Maintenance notices](#maintenance-notices-repairs-and-health-sensors));
  after an app update they are transmitted automatically.
- Otherwise `unknown`, `unavailable`, `none` and empty states are not
  archived.

Resolution, retention and cleanup thresholds do not belong in this filter.
They are configured globally or per entity in the app.

## Settings menu

**Configure** opens a compact menu with four actions:

1. **Edit archive filters** – change the active selection.
2. **Currently included entities** – review the resolved selection and rounding.
3. **Export filters as YAML** – show a portable copy.
4. **Import filters from YAML** – replace all filters with a copy.

You normally select entities directly in the UI via **Edit archive filters**.
The YAML export and import is optional and only serves to transfer the same
selection to another system.

### YAML export for test systems

The export contains only the filters and never host, port or API token. The
displayed content can be copied and saved as a `.yaml` file:

```yaml
format: zeitarchiv-options
version: 3
filters:
  labels:
    - zeitarchiv
  entities:
    - sensor.outdoor_temperature
  areas: []
  devices: []
  exclude_entities:
    - sensor.test_value
  entity_patterns:
    - sensor.weather_*
  exclude_entity_patterns:
    - "*_id"
```

The import uses a safe YAML loader and validates format version, structure,
entity IDs and patterns. Exports of the previous format versions 1 and 2
remain importable; any domains they contain are converted once into currently
known entity IDs. Only after successful validation does the import replace
the options and reload the integration.

> [!NOTE]
> Entity IDs are usually directly transferable between identically structured
> systems. Labels, areas and devices reference internal registry IDs and only
> work on the target system if these IDs match.

## Queue and error behavior

| Property | Value |
| --- | ---: |
| Maximum queue | 5,000 events |
| Batch size | 100 events |
| Batch timeout | 5 seconds |
| Retry intervals | 1, 2, 4, 8, 15, 30, then 60 seconds |

The worker runs in its own thread and does not block the Home Assistant event
loop. A failed batch is kept and retried without a fixed retry limit. On
unload, the integration tries to drain the queue and any partial batch in a
controlled way.

If the queue is full, newly arriving events are dropped and counted. The queue
is not persistent; a restart discards values that have not yet been
transmitted.

## Diagnostics in Home Assistant

On the integration's device page, four sensors appear under **Diagnostic**:

| Sensor | Meaning |
| --- | --- |
| Last transmission | Time of the last acknowledged batch |
| Transferred records (since start) | Events acknowledged by the app; retries are not counted twice |
| Queue | Events still waiting in the background worker |
| Dropped events (since start) | Events dropped because the queue was full or stopped |

Both counters start at zero after each start of the integration.

In addition, **Download diagnostics** can be chosen on the integration tile.
The report contains:

- a current connection test;
- queue size, last error and last success;
- events sent and dropped since start;
- the number of entities currently covered by the filters;
- the saved options.

The API token is redacted automatically.

## Maintenance notices: Repairs and health sensors

Both paths read the same notices from the app (`/api/notices`, polled every
60 s) but serve different purposes — only one subset becomes a repair card,
another (overlapping) subset becomes automatable entities:

**Three `binary_sensor` health entities** on the Zeitarchiv device, deliberately
**not** diagnostic entities (so they remain easy to find on the regular
dashboard and for automations):

| Sensor | Turns on when |
| --- | --- |
| Backup failed | the last backup run failed, or the backup could not be transferred to the app's external target |
| Entities inactive | one or more entities have not reported for several days (info/warn/error combined) |
| Maintenance notice | storage index reconciliation error, failed retention run, recommended cleanup, low host disk space, recommended index optimization |

Each sensor carries the exact notice IDs and texts currently triggering it as
the attribute `reasons`/`details` — useful when several causes apply at once.

**Home Assistant Repairs** (Settings → System → Repairs) cover only the
genuinely critical cases that call for a deliberate response: failed backup,
failed retention run, long-inactive entities (critical level only), outdated
integration version, and critically low host disk space. Deliberately no
interactive fix flows — the actual remedy (re-running the backup, checking
retention, updating the integration) happens in the Zeitarchiv app or via
HACS; the repair card serves as a notice with instructions in its text.

**One exception does not come from the notices:** the repair issue "Zeitarchiv
connection paused" (see [Changing the token](#changing-the-token)) arises on
its own directly from the write path, because the normal notice-based path is
itself unreachable at exactly that moment (rejected token). Likewise straight
from the write path comes "Zeitarchiv: entities with text values are not
archived yet": it lists individually selected entities whose state is text
instead of a number, as long as the connected app cannot accept states yet —
the app then never learns about them. The card disappears by itself after an
app update, or once none of these entities reports text anymore. The `binary_sensor` **Non-archivable entities** on the
Zeitarchiv device shows the same for dashboards and automations: "OK" as long
as all selected entities report archivable values, otherwise "Problem". The
attributes `entities` (full list) and `count` name the affected entities; the
sensor updates immediately, not on the 60 s cycle.

## Operating mode

The **Operating mode** sensor on the Zeitarchiv device shows whether the
connected app instance is currently running in production or in demo mode (a
synthetic showcase/test instance with its own data directory, see the
Zeitarchiv app documentation). Useful for recognizing, in automations or at a
glance on the dashboard, that you are on a showcase instance rather than the
real installation. Deliberately not a diagnostic entity, for the same reason as
the backup sensor below. If the app is currently unreachable, the entity shows
the Home Assistant default state "Unavailable" instead of a wrong value.

## Offsite backup via automation

Zeitarchiv can copy backups to a network share (NFS/SMB) or a WebDAV server
itself (page **Backup → External target** in the app). That needs no
automation, and the integration reports the result: the **Latest backup**
sensor carries the attributes `external_status` (`ok`, `failed` or `running`;
empty if no external target is set up), `external_target` and
`external_finished_at`, and **Backup failed** also turns on when only the
external copy is missing.

For everything the app cannot do (S3, cloud services, your own scripts), the
integration provides an automation trigger: the **Latest backup** sensor
(state = timestamp of the last SUCCESSFUL backup, attributes
`filename`/`size_bytes`) — deliberately not a diagnostic entity, so it is easy
to find in automations.

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fbertel2020%2FHA-Zeitarchiv%2Fmain%2Fblueprints%2Fautomation%2Fzeitarchiv%2Fbackup_upload.yaml)

After importing: select the backup sensor of the desired connection and enter
your own upload action, e.g. a `shell_command` with `rclone copy`:

```yaml
shell_command:
  rclone_backup_upload: "rclone copy '/config/zeitarchiv-backups/{{ filename }}' remote:zeitarchiv-backups/"
```

In the blueprint action, file name and size are available via template:
`{{ trigger.to_state.attributes.filename }}` and
`{{ trigger.to_state.attributes.size_bytes }}`.

## Changing the token

If the token is regenerated in the app, the app rejects the next batch. The
integration then starts the Home Assistant reauth flow; the pending batch is
kept. Simply enter the new token in the dialog that appears.

**Exception: demo mode.** When the app is switched to [demo mode](#operating-mode),
its token changes as well — but this deliberately does **not** trigger a
reauth: the integration recognizes the reason itself (no real token problem)
and instead pauses quietly, indicated by a dedicated notice under Settings →
Repairs. As soon as the app is switched back to production, the connection
resumes sending on its own — with the original token, without anything to
update here. Only if this cannot be determined unambiguously does the usual
reauth dialog ask — and then additionally warns if the newly entered token
happens to belong to a demo instance.

Connection name, host, port and token can also be changed at any time via the
integration tile → **Reconfigure**. The connection is tested again before the
change is applied.

## Filter logic in detail

An entity is archived if it is not explicitly excluded and satisfies at least
one inclusion rule:

```text
not excluded
        AND
(domain selected OR entity ID selected OR resolved via area/device
 OR include pattern matches)
```

Patterns without a dot are applied to the object ID after the domain: `*_id`,
for example, matches `sensor.device_id` and `input_number.user_id`. Patterns
with a dot check the full entity ID, so `sensor.*_id` only covers sensors. Only
`*` and `?` are supported; regular expressions are deliberately not allowed.

Areas and devices are resolved into concrete entity IDs when the options are
saved. Entities that are newly added to a selected area or device later are
only taken into account after the filters are saved again.

## Dashboard card

The integration ships a Lovelace card that shows a saved chart from Zeitarchiv. No
resource needs to be added.

1. In the dashboard choose **Add card → Zeitarchiv**.
2. Pick the chart in the editor. Title, refresh (default 60 seconds) and height are
   optional.

```yaml
type: custom:zeitarchiv-card
chart_id: 12
title: Power consumption
refresh: 60
height: 260
```

**Entities directly:** Instead of a saved chart, the editor lets you choose entities, period and display (source
"Entities directly"). Only entities archived by Zeitarchiv are offered.

```yaml
type: custom:zeitarchiv-card
entities:
  - sensor.grid_import
  - sensor.feed_in
period: month        # day, week, month, year, 24h, 7d, 30d
style: stacked       # auto (per entity), stacked, percent (shares in percent)
```

- **Administrators only.** Home Assistant has no per-chart permissions, so the card
  shows nothing to other users.
- **Only the integration talks to Zeitarchiv.** The card never contacts the app; it
  goes through Home Assistant and the token stays in the integration. The app needs
  the "cards" capability for this (update the app if the card says so).
- **What the card draws:** every view of a saved chart: numbers as line, bars, stacked and as shares in percent,
  with previous period, previous year and multi-year comparison, plus timeline, donut and, for states, shares,
  changes and heatmap. Tooltips, light and dark theme. The period saved with the chart applies. Saved comparison tables are shown with the same cells, formulas and
  styles as in the tile (source "Saved table", `table_id`); the hover hints of the table are not in the card yet.
- If the app is unreachable, the last image stays and the card shows its age.

### History under a tile card

There is also a small history line as a **feature** of the standard tile card: in the tile card choose
**Add feature → Zeitarchiv history**. It shows the tile's entity for the last 24 hours, 7 or 30 days as line, area or
bars, optionally with marked minimum and maximum and the change. The entity must be archived by Zeitarchiv; otherwise
it says "Not archived".

```yaml
type: tile
entity: sensor.outside_temperature
features:
  - type: custom:zeitarchiv-sparkline
    range: 24h          # 24h, 7d, 30d
    style: line         # line, area, bars
    color: accent       # accent or trend (green rising, red falling)
    min_max: true
    show_change: true
```

Like the card, visible to administrators only.

## Known limitations

- Non-numeric text sensors are not archived; selected ones are reported as a
  repair card.
- Area and device assignments are not continuously re-resolved.
- Queue and transmission counters exist only for the lifetime of the integration.
- The connection uses a shared static token, not OAuth.
- The integration is a write path; archived values are not read back as new
  Home Assistant entities. The card shows saved charts but does not turn them into
  entities.

## Removal

1. Open **Settings → Devices & services → Zeitarchiv** and choose
   **⋮ → Delete** on the entry. With several connections, delete each one.
2. If installed via HACS, also remove the integration in HACS; for a manual
   installation, delete the `/config/custom_components/zeitarchiv` folder.
3. Restart Home Assistant.

Deleting a connection removes its service device, its diagnostic and health
sensors and its repair cards. Values still waiting in the queue at that moment
are no longer transmitted.

The archive itself is left untouched: all values transmitted so far live in
the Zeitarchiv app and stay there. To remove them as well, uninstall the app
separately. The API token can be regenerated in the app under
**Settings → Connection** so the old one is no longer valid.

---

<p align="center">
  <a href="https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv">Zeitarchiv app</a>
  ·
  <a href="https://github.com/bertel2020/HA-Apps/blob/main/zeitarchiv/CHANGELOG.md">App changelog</a>
</p>

## License

This project is licensed under the [MIT License](LICENSE).
Copyright 2026 Roberto / bertel2020.
