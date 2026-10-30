# Changelog

## Unreleased

### Neu

- **Zeitarchiv-Karte für Lovelace** (`custom:zeitarchiv-card`, nur für
  Administratoren, braucht eine aktuelle Zeitarchiv-App): Zeigt ein gespeichertes
  Chart oder eine gespeicherte Tabelle des Zeitarchivs direkt im Dashboard, im
  Hell- und Dunkelmodus und mit den Beschriftungen der Home-Assistant-Sprache.
  Die Karte lässt sich im Karteneditor einrichten.
  - **Entitäten direkt**: Statt eines gespeicherten Charts lassen sich bis zu
    zehn archivierte Entitäten mit Zeitraum und Darstellung wählen.
  - **Darstellungen**: Linien, Balken, gestapelt und in Prozent, Vergleich mit
    Vorperiode oder Vorjahr, Zeitstrahl, Zustände, Heatmap und Donut.
  - **Ausfälle**: Ist die App nicht erreichbar, zeigt die Karte den letzten
    Stand mit Hinweis und versucht es mit wachsendem Abstand erneut.
- **Sparkline für Kachelkarten**: Als zusätzliche Funktion der normalen
  Home-Assistant-Kachelkarte zeigt eine kleine Sparkline den Verlauf einer
  archivierten Zahlen-Entität (24 Stunden, 7 oder 30 Tage).

---

### English

#### New

- **Zeitarchiv card for Lovelace** (`custom:zeitarchiv-card`, administrators
  only, needs a current Zeitarchiv app): Shows a saved chart or a saved table
  of Zeitarchiv directly on your dashboard, in light and dark mode and with
  labels in the Home Assistant language. The card can be set up in the card
  editor.
  - **Entities directly**: Instead of a saved chart you can pick up to ten
    archived entities with a period and a display style.
  - **Displays**: Lines, bars, stacked and in percent, comparison with the
    previous period or year, timeline, states, heatmap and donut.
  - **Outages**: If the app cannot be reached, the card keeps showing the last
    state with a notice and retries at growing intervals.
- **Sparkline for tile cards**: As an extra feature of the regular Home
  Assistant tile card, a small sparkline shows the history of an archived numeric
  entity (24 hours, 7 or 30 days).

## 1.2.1 - 2026-10-25

### Behoben

- **Thermostate fehlten bei Auswahl über Label, Gerät oder Bereich**:
  Heizkörperthermostate und andere Klimageräte (`climate`) werden jetzt auch
  dann archiviert, wenn du sie über ein Label, ein Gerät, einen Bereich oder
  ein Muster auswählst. Ihr Zustand (z. B. „heat“, „auto“, „off“) ist Text und
  wurde bisher nur bei Einzelauswahl übernommen. Andere Textentitäten
  erfasst weiterhin nur die Einzelauswahl.

---

### English

#### Fixed

- **Thermostats were missing when selected by label, device or area**:
  Radiator thermostats and other climate devices (`climate`) are now archived
  even when you select them by label, device, area or pattern. Their state
  (e.g. “heat”, “auto”, “off”) is text and was previously only taken over when
  selected individually. Other text entities are still only covered by
  individual selection.

## 1.2.0 - 2026-10-25

### Neu

- **Auswahl-Assistent**: Zusammen mit der Zeitarchiv-App lassen sich Entitäten
  jetzt dort auswählen statt in den Optionen der Integration.
  - **Katalog**: Die Integration schickt der App eine Liste der archivierbaren
    Entitäten mit Name, Art, Gerät und Bereich, ohne Messwerte. Das geschieht
    höchstens alle zehn Minuten und nur, wenn die App es unterstützt.
  - **Übernehmen**: Bestätigte Vorschläge setzt die Integration innerhalb etwa
    einer Minute um, standardmäßig über das Label „Zeitarchiv“ in Home
    Assistant (wirkt ohne Neustart), alternativ als Einzel-ID. Textentitäten und
    Entitäten ohne Registry-Eintrag gehen immer als Einzel-ID. Neu ausgewählte
    Entitäten senden ihren aktuellen Zustand sofort nach.
  - **Ausschließen und Muster**: Die App kann Entitäten ausschließen und wieder
    aufnehmen sowie Muster wie `sensor.shelly_plug_*` hinzufügen und entfernen.
    Textentitäten erfasst ein Muster weiterhin nicht.
  - **Herkunft**: Die Integration merkt sich, was der Assistent ausgewählt hat,
    und erkennt Änderungen, die du in Home Assistant machst, auch an Labels,
    Bereichen und Geräten. Die App zeigt sie im Verlauf.
- Braucht die Zeitarchiv-App ab 1.11.0. Mit einer älteren läuft alles wie zuvor.

---

### English

#### New

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

### Neu

- **KI-Zugriff**: Zeitarchiv steht als API für den MCP Server von Home
  Assistant bereit. Claude, ChatGPT oder der Gesprächsagent von Home Assistant
  können damit Fragen zum Archiv beantworten, rein lesend. Welche Werkzeuge
  und Texte angeboten werden, bestimmt die App unter Einstellungen →
  KI-Zugriff; Ein- und Ausschalten wirkt ohne Neustart von Home Assistant.
  Braucht die Zeitarchiv-App ab 1.9.0.
- **Zustände**: Entitäten, die Text statt einer Zahl liefern (z. B. ein
  Thermostat mit „Heizen“/„Leerlauf“), werden an die App übertragen, wenn sie
  einzeln ausgewählt sind, auch „nicht verfügbar“. Braucht die App ab 1.9.0;
  bei einer älteren App erscheint wie bisher eine Reparatur-Karte samt
  Binärsensor „Nicht archivierbare Entitäten“. Werden Werte verworfen, weil
  der Typ nicht passt oder eine Entität mehr als 50 Zustände liefert, meldet
  eine Reparatur-Karte das.
- Lichter, Ventilatoren, Automationen, Skripte, Fernbedienungen, Sirenen,
  Luftbefeuchter, Updates und Kalender werden wie Schalter (an/aus)
  übertragen. Bisher kamen sie nicht in der App an.

### Geändert

- Ein abgelehnter Token beim Start löst jetzt die erneute Anmeldung aus,
  statt still nichts zu übertragen.
- Dieselbe Verbindung (gleicher Host, Port und Token) lässt sich nicht
  zweimal einrichten. Beim Entfernen einer Verbindung wird ihr gemerkter
  Übertragungsstand mit gelöscht.
- Fällt die App aus, meldet die Integration das einmal und die
  Wiederherstellung einmal, statt alle zehn Minuten zu warnen.

---

### English

#### New

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

#### Changed

- A rejected token at startup now starts the re-authentication instead of
  silently transferring nothing.
- The same connection (same host, port and token) cannot be set up twice.
  Removing a connection also deletes its stored transfer position.
- If the app is unreachable, the integration reports it once and the recovery
  once, instead of warning every ten minutes.

## 1.0.0 - 2026-10-19

### Geändert

- Neues Icon und Logo, passend zum neuen Logo der Zeitarchiv-App.

### Behoben

- Lehnte die App ein einzelnes Ereignis ab, etwa wegen eines Texts mit mehr
  als 255 Zeichen, blieb die ganze Übertragung daran hängen: Die
  Warteschlange lief voll, und neue Zustandsänderungen aller Entitäten gingen
  verloren. Überlange Texte werden jetzt gekürzt, und ein abgelehnter Batch
  wird verworfen, statt die übrigen aufzuhalten.

---

### English

#### Changed

- New icon and logo, matching the new logo of the Zeitarchiv app.

#### Fixed

- If the app rejected a single event, for example because of a text longer
  than 255 characters, the whole transfer got stuck on it: the queue filled up
  and new state changes of all entities were lost. Overlong texts are now
  shortened, and a rejected batch is dropped instead of holding up the rest.

## 0.20.0 - 2026-10-11

### Neu

- Der Sensor **Letztes Backup** zeigt jetzt auch den Stand der Kopie auf dem
  externen Backup-Ziel der App (Netzwerkspeicher oder WebDAV): als Attribute
  `external_status`, `external_target` und `external_finished_at`. Ohne
  externes Ziel oder mit einer älteren App sind sie leer.
- Der Binary-Sensor **Backup fehlgeschlagen** schaltet jetzt auch, wenn die
  Übertragung auf das externe Ziel scheitert. Das lokale Backup ist dann in
  Ordnung, die App versucht die Übertragung beim nächsten Backup erneut.
- Die Blueprint-Beschreibung für den Backup-Upload ist angepasst: NFS, SMB und
  WebDAV übernimmt die App selbst, das Blueprint bleibt für andere Ziele wie
  S3 oder Cloud-Dienste.

---

### English

#### New

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

### Neu

- Die Integration übermittelt die Sprache von Home Assistant an die
  Zeitarchiv-App (Header `Accept-Language`). Fehlermeldungen der App
  erscheinen dadurch in der Sprache deiner Home-Assistant-Installation
  (Deutsch oder Englisch).

---

### English

#### New

- The integration sends the Home Assistant language to the Zeitarchiv app
  (`Accept-Language` header). Error messages from the app therefore appear in
  the language of your Home Assistant installation (German or English).

## 0.18.2 - 2026-09-15

### Geändert

- **Wartungshinweis** erkennt jetzt zusätzlich eine hohe Duplikatquote bei
  der Datenübertragung.

### Behoben

- Ein Neuladen (z. B. nach einer Änderung der Filter-Einstellungen) sendete
  bislang den aktuellen Zustand jeder erfassten Entität erneut, auch ohne
  echte Änderung — bei vielen Entitäten konnte das die verbundene App
  kurzzeitig überlasten. Die Integration merkt sich jetzt, was zuletzt
  erfolgreich übertragen wurde, und überspringt unveränderte Werte.

## 0.18.1 - 2026-09-11

### Neu

- **Wartungshinweis** erkennt jetzt zusätzlich eine empfohlene
  Index-Optimierung.

### Geändert

- Binary-Sensor „Entitäten inaktiv" heißt jetzt „Inaktive Entitäten
  erkannt".

### Entfernt

- Repair-Hinweis „Zeitarchiv-Import fehlgeschlagen": ein Import läuft
  interaktiv in der App, sein Ergebnis ist dort direkt sichtbar.

### Behoben

- Der Sensor **Betriebsmodus** zeigte sich selbst „Nicht verfügbar",
  sobald die verbundene App in den Demo-Modus wechselte. Er zeigt jetzt
  zuverlässig „Demo"; die Health-Sensoren zeigen währenddessen „Unbekannt"
  statt fälschlich „Aus".

## 0.18.0 - 2026-09-09

### Neu

- Schaltet die verbundene App in den Demo-Modus um, löst das bei
  bestehenden Verbindungen keinen unnötigen Reauth-Dialog mehr aus. Die
  Integration erkennt den Grund selbst und pausiert stattdessen ruhig
  (sichtbar unter Einstellungen → Repairs), bis die App zurück auf
  Produktiv geschaltet wird — dann sendet die Verbindung von selbst
  wieder, ohne dass etwas nachgepflegt werden muss.

## 0.17.0 - 2026-09-09

### Neu

- `device_tracker`- und `person`-Entitäten sind jetzt archivierbar. Sie
  gelten wie Schalter: „Zuhause" wird als „an" gewertet, jeder andere
  Zustand (unterwegs oder eine benannte Zone) als „aus".
- Neuer Sensor **Betriebsmodus** am Zeitarchiv-Gerät zeigt, ob die
  verbundene App-Instanz gerade produktiv oder im Demo-Modus läuft (siehe
  App-Dokumentation) — nützlich, um in Automationen oder per Blick aufs
  Dashboard eine Vorführinstanz von der echten Anlage zu unterscheiden.

## 0.16.0 - 2026-09-08

### Neu

- Neuer Sensor **Letztes Backup** am Zeitarchiv-Gerät (Zeitpunkt, Dateiname,
  Größe) sowie ein importierbares Automations-Blueprint, um Backups darüber
  automatisch an ein externes Ziel zu kopieren (z. B. mit `rclone`) — siehe
  README, Abschnitt "Offsite-Backup per Automation".

## 0.15.1 - 2026-09-03

### Geändert

- Die neue App-Meldung für knappen Host-Speicherplatz fließt jetzt durch
  dieselbe Rückkopplung wie die übrigen Health-Zustände: ab kritischem
  Füllstand als Home-Assistant-Repair, bereits ab der Warnstufe als Teil des
  gebündelten `binary_sensor`-Wartungshinweises.

## 0.15.0 - 2026-09-03

### Neu

- Neue Health-Entities (`binary_sensor`) am Zeitarchiv-Gerät: fehlgeschlagenes
  Backup, lange inaktive Entitäten sowie ein gebündelter Wartungshinweis
  (Speicherabgleich, Aufbewahrung, Aufräumen empfohlen) — direkt in
  Automationen nutzbar.
- Kritische Zustände (fehlgeschlagenes Backup/Aufbewahrung/Import, lange
  inaktive Entitäten, veraltete Integration) erscheinen zusätzlich als
  Home-Assistant-Repair unter Einstellungen → Repairs.
- Die Integration schickt ihre Version bei jeder Anfrage an die App mit; die
  App zeigt sie in ihren Verbindungs-Einstellungen an und weist auf
  veraltete Integrationsversionen hin.

## 0.14.0 - 2026-08-30

### Neu

- Labels sind die bevorzugte Archivfilter-Auswahl. Direkt gelabelte Entitäten
  sowie Entitäten gelabelter Geräte und Bereiche werden bei folgenden
  Zustandsänderungen ohne erneutes Speichern erfasst.
- Der Archivfilter verwendet native, einklappbare Home-Assistant-Bereiche und
  zeigt die konfigurierten Nachkommastellen auch in Vorschau und Übersicht.

### Geändert

- Domainfilter wurden entfernt. Gespeicherte Domainauswahlen und ältere
  YAML-Exporte werden einmalig in aktuell bekannte Entity-IDs umgewandelt.
- Das portable Filterformat wurde auf Version 3 angehoben; Version 1 und 2
  bleiben importierbar.

## 0.13.0 - 2026-08-29

### Neu

- Die Anzahl der bei der Übertragung verwendeten Nachkommastellen (0–3) ist
  im Options-Flow unter **Archivfilter bearbeiten** einstellbar, inklusive
  Empfehlung und Hinweis auf die Auswirkung auf den Speicherverbrauch in der
  App. Der bisherige Festwert von drei Nachkommastellen bleibt der Standard.

## 0.12.0 - 2026-08-25

### Behoben

- Das Logo in der von HACS gerenderten README verwendet eine absolute
  Raw-GitHub-URL und wird dadurch unabhängig vom Basis-Pfad des Renderers
  geladen.

## 0.11.0 - 2026-08-25

### Neu

- Archivfilter unterstützen Einschluss- und Ausschlussmuster mit `*` und `?`.
- Vor dem Speichern zeigt der Options-Flow die tatsächlich aufgelösten,
  derzeit zustandslosen und ausgeschlossenen Entity-IDs an; damit werden auch
  alle Entitäten ausgewählter Bereiche und Geräte sichtbar.
- Derselbe Entitätenreport kann über einen eigenen Eintrag im Einstellungsmenü
  jederzeit für die gespeicherten Filter geöffnet werden.

## 0.10.0 - 2026-08-25

### Neu

- Beim Laden oder Neuladen eines Integrationseintrags werden die aktuellen
  Zustände aller passenden Entitäten sofort an die Zeitarchiv-App übertragen.

### Geändert

- Numerische Werte werden vor der Übertragung auf maximal drei
  Nachkommastellen begrenzt.
