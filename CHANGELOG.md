# Changelog

> Deutsche Version: [CHANGELOG.de.md](CHANGELOG.de.md)

## 1.5.0 - 2026-11-10

### New

- **Card: legend**: The legend of the chart card can be switched off and shown
  in two sizes
  - Legend style "Off" hides the legend completely
  - Legend size "As in the chart", "Normal" or "Small"; without a setting the
    size of the chart applies
- **Card: more sensors by room and floor**: The weather dashboard table groups
  the sensors by room, rooms can be collapsed and sit below their floor from
  Home Assistant (needs Zeitarchiv 1.40.0)
- **Card: tables**: The card follows the tables of the app
  - New row aggregation "Current value", decimals of the entity for the
    column "Auto"
  - Columns "Today" and "Yesterday", the previous-year menu and column heads as
    in the app, single years with their own head
- **Card: charts**: Adjustments to the app
  - The monthly comparison shows at most the last five earlier years, all of
    them are in the legend, older years fainter
  - Monthly chart with selectable decimals
  - New record days "Days without grid import" and "High feed-in", years
    without storage; heatmap with a colour gradient and text for empty cells,
    February 29 grey in the yearly matrix
  - Records without a minimum archive length, with their own text when there
    are none yet

## 1.4.2 - 2026-11-08

### Fixed

- **Card: energy date selection**: The card follows the date again after a view
  change or edit mode
  - "This week" showed the previous week from the fourth weekday on
- **Card: editor**: The settings of an element (period, role, values) are no
  longer lost when the list of elements could not be loaded
- **Card: tables**: A loading error is shown as an error instead of empty
  cells; the legend of a previous chart no longer stays below a table
- **Card: legend**: Keyboard focus is kept after toggling an entry; in the year
  comparison the previous year runs up to the same day, and the year is
  correct even if the browser is in a different time zone
- **Card: dashboard elements**: Users who are not administrators see the
  notice that elements are visible to administrators only, instead of a hint
  about "Share card"

## 1.4.1 - 2026-11-05

### Changed

- **Card: editor for dashboard elements**: The fields of an element are now
  labelled "Columns", "Compare with last year", "Show difference" and so on
  instead of "columns", "vorjahr" and "diff"
  - Short hints explain what previous year, difference, periods back and the
    date selection of the energy dashboard do
  - The title names the element as its default, for a table the table
  - Refresh, height and tap action sit collapsed under "More settings", for all
    sources of the card; refresh and height name their default when the field is
    empty
  - A sentence below the element says what it shows
  - Period, periods back and the date selection of the energy dashboard sit
    together in a section of their own, style and values of the legend collapsed
    under "Customize legend"
- **Card: description**: In the dialog for adding a card, the description now
  also mentions tables and dashboard elements

### Fixed

- **Card: legend with a single series**: "Show legend" now also works on a chart
  with only one entity. Without a setting it stays as before, without a legend
- **Card: legend with values on a chart**: The chips ran together without
  spacing or borders ("WirkleistungAktuell 574,8 WMin …") when the card showed
  only a chart. They now look like on the tile in the app

## 1.4.0 - 2026-11-05

### New

- **Card: dashboard elements**: New source "Dashboard element" in the card
  editor. The card shows periods compared from the energy and weather dashboards,
  years × months from energy, as well as the monthly comparison (energy, weather)
  the weather year overview, the shares and the daily load profile from energy
  as a chart, as well as key-figure tiles from energy and weather, with the
  figures of the app.
  - In the editor, columns, previous year and difference can be chosen; for the
    matrix and the monthly comparison the value and years, for weather the group
    or measure, for shares, load profile and energy key figures the period and
    offset, for the key figures the values and the trend
  - The energy key figures also offer self-sufficiency, self-consumption and the
    storage; without a choice they stay the four energy amounts
  - A new, larger storage card shows a battery symbol and, for a day, the curve
    of the state of charge
  - The energy long-term adds records, key days per year and "What has
    changed?"; for key days you choose the years and "until today" or whole
    years, for the changes the number of consumers
  - Optionally, shares and load profile follow the date selection of the Home
    Assistant energy dashboard; without it, the period of the card applies
  - Only administrators see elements; if an element is not set up in the app,
    the card says so
  - Needs the current app; with an older one the card reports that the app is
    too old

- **Card: legend with values**: Below the chart, the card shows chips or a table
  with current, min, max, average and total, like the dashboard tile in the app.
  Clicking an entry shows or hides the series.
  - In the card editor, style and values can be chosen under "Show legend"; empty
    means as in the chart
  - On a narrow card, "As in the chart" shows chips instead of a table
  - The legend with values needs the current app; with an older one, the legend
    with names stays

## 1.3.3 - 2026-11-03

### Fixed

- **Nothing is lost on shutdown or reload**: If states had not yet been
  delivered to the app, for example because it was unreachable, they were lost
  when Home Assistant restarted or the integration was reloaded. They are now
  saved and resent on the next start.

- **Reauth for a rejected token**: The re-authentication notice now also
  appears when there is currently nothing to write.

- **Card, keyboard and cleanup**: Enter or Space on a legend entry no longer
  triggers the card's tap action and toggles the series as usual. If the card
  is removed while data is loading, it no longer draws into nothing. Year,
  month and day boundaries follow the server's time zone.

### Changed

- **Lower load**: State changes are filtered in the event loop instead of the
  thread pool, and the "last sent" state is written less often (easier on SD
  cards).

- **AI access, user accounts**: Anyone connecting with an account without
  administrator rights (for example a family account) is no longer offered the
  tools for individual entities, as with the card. The energy overview and the
  notices remain available. Administrators and Home Assistant's local
  conversation agent are not affected.

## 1.3.2 - 2026-11-01

### Fixed

- **Zeitarchiv card on Home Assistant 2026.10**: The card was missing from the
  card picker and the dashboard, or showed up only at random (console: "Custom
  element not found: zeitarchiv-card"), depending on browser and load timing.
  The cause is in the Home Assistant 2026.10 frontend and is fixed from 2026.11
  on. The card and the sparkline now register themselves again after the app
  has started if needed, so they also work on 2026.10.

## 1.3.1 - 2026-11-01

### Fixed

- **Zeitarchiv card, Wh and kWh**: Series in Wh and kWh in the same chart ended
  up on two separate axes with their own scale and could not be compared. They
  now share one axis in the largest unit present; pure Wh charts stay in Wh.
- **Zeitarchiv card**: The card files are no longer cached in the browser for
  up to 31 days. After an update this makes it less likely that an old card
  version gets stuck and shows only a loading spinner in the card picker. The
  documentation now describes what to do in that case.

## 1.3.0 - 2026-10-31

### New

- **Zeitarchiv card for Lovelace** (`custom:zeitarchiv-card`, needs
  Zeitarchiv app 1.12.0 or later): Shows a saved chart or a saved table
  of Zeitarchiv directly on your dashboard, in light and dark mode and with
  labels in the Home Assistant language. The card can be set up in the card
  editor; the card picker already shows a preview with your first chart. In
  the sections layout it takes the full width and its own height. Screen
  readers read names and values for every chart. On tap, the card can run a
  Home Assistant action if you like, for example open another dashboard. Update
  the app first, then the integration.
  - **Share with all users**: By default only administrators see the card. In
    the integration settings under **Share card** you choose charts and tables
    that every signed-in user sees, for example on a wall tablet. Entities
    directly stay with administrators.
  - **Entities directly**: Instead of a saved chart you can pick up to ten
    archived entities with a period and a display style.
  - **Displays**: Lines, bars, stacked and in percent, comparison with the
    previous period or year, timeline, states, heatmap and donut.
  - **Outages**: If the app cannot be reached, the card keeps showing the last
    state with a notice and retries at growing intervals.
- **Sparkline for tile cards**: As an extra feature of the regular Home
  Assistant tile card, a small sparkline shows the history of an archived numeric
  entity (24 hours, 7 or 30 days). It is visible to all users.

## 1.2.1 - 2026-10-25

### Fixed

- **Thermostats were missing when selected by label, device or area**:
  Radiator thermostats and other climate devices (`climate`) are now archived
  even when you select them by label, device, area or pattern. Their state
  (e.g. “heat”, “auto”, “off”) is text and was previously only taken over when
  selected individually. Other text entities are still only covered by
  individual selection.

## 1.2.0 - 2026-10-25

### New

- **Selection assistant**: Together with the Zeitarchiv app, entities can now be
  chosen there instead of in the integration's options.
  - **Catalog**: The integration sends the app a list of archivable entities
    with name, type, device and area, without measured values. This happens at
    most every ten minutes and only if the app supports it.
  - **Applying**: Confirmed suggestions are applied by the integration within
    about a minute, by default through the label “Zeitarchiv” in Home Assistant
    (takes effect without a restart), alternatively as an individual ID. Text
    entities and entities without a registry entry are always added as an
    individual ID. Newly selected entities send their current state right away.
  - **Exclude and patterns**: The app can exclude entities and include them
    again, and add and remove patterns such as `sensor.shelly_plug_*`. A pattern
    still does not cover text entities.
  - **Origin**: The integration remembers what the assistant selected and
    detects changes you make in Home Assistant, including changes to labels,
    areas and devices. The app shows them in its history.
- Needs the Zeitarchiv app 1.11.0 or later. With an older one everything works as
  before.

## 1.1.0 - 2026-10-22

### New

- **AI access**: Zeitarchiv is available as an API for Home Assistant's MCP
  server. Claude, ChatGPT or Home Assistant's conversation agent can use it to
  answer questions about the archive, read-only. Which tools and texts are
  offered is decided by the app under Settings → AI access; switching it on or
  off takes effect without restarting Home Assistant. Needs the Zeitarchiv app
  1.9.0 or later.
- **States**: entities that report text instead of a number (e.g. a thermostat
  with "Heating"/"Idle") are sent to the app when they are selected
  individually, including "unavailable". Needs app 1.9.0 or later; with an
  older app, a repair card and the binary sensor "Non-archivable entities" appear
  as before. When values are discarded because the type does not match or an
  entity reports more than 50 states, a repair card says so.
- Lights, fans, automations, scripts, remotes, sirens, humidifiers, updates
  and calendars are sent like switches (on/off). Previously they never reached
  the app.

### Changed

- A rejected token at startup now starts the re-authentication instead of
  silently transferring nothing.
- The same connection (same host, port and token) cannot be set up twice.
  Removing a connection also deletes its stored transfer position.
- If the app is unreachable, the integration reports it once and the recovery
  once, instead of warning every ten minutes.

## 1.0.0 - 2026-10-19

### Changed

- New icon and logo, matching the new logo of the Zeitarchiv app.

### Fixed

- If the app rejected a single event, for example because of a text longer
  than 255 characters, the whole transfer got stuck on it: the queue filled up
  and new state changes of all entities were lost. Overlong texts are now
  shortened, and a rejected batch is dropped instead of holding up the rest.

## 0.20.0 - 2026-10-11

### New

- The **Last backup** sensor now also shows the state of the copy on the app's
  external backup target (network storage or WebDAV), as the attributes
  `external_status`, `external_target` and `external_finished_at`. They are
  empty without an external target or with an older app.
- The **Backup failed** binary sensor now also turns on when the transfer to
  the external target fails. The local backup is fine in that case; the app
  retries the transfer with the next backup.
- The description of the backup upload blueprint is updated: the app handles
  NFS, SMB and WebDAV itself, the blueprint remains for other targets such as
  S3 or cloud services.

## 0.19.0 - 2026-10-07

### New

- The integration sends the Home Assistant language to the Zeitarchiv app
  (`Accept-Language` header). Error messages from the app therefore appear in
  the language of your Home Assistant installation (German or English).

Versions before the first bilingual one are in German only: see [CHANGELOG.de.md](CHANGELOG.de.md).
