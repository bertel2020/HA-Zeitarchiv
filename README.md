<p align="center">
  <img src="https://raw.githubusercontent.com/bertel2020/HA-Zeitarchiv/main/custom_components/zeitarchiv/brand/logo.png" alt="Zeitarchiv" width="160">
</p>

<h1 align="center">Zeitarchiv Integration</h1>

<p align="center">
  Der zuverlässige Schreibpfad von Home Assistant in das Zeitarchiv.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <a href="https://github.com/bertel2020/HA-Zeitarchiv/releases"><img src="https://img.shields.io/github/v/release/bertel2020/HA-Zeitarchiv?sort=semver" alt="Release"></a>
  <a href="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/validate.yml"><img src="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/tests.yml"><img src="https://github.com/bertel2020/HA-Zeitarchiv/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/bertel2020/HA-Zeitarchiv" alt="License"></a>
</p>

Die Zeitarchiv-Integration beobachtet ausgewählte Zustandsänderungen und
überträgt sie gebündelt an die [Zeitarchiv-App](https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv). Sie
erzeugt keine Kopien der archivierten Entitäten in Home Assistant: Die
eigentlichen Zeitreihen, Charts und Tabellen bleiben Aufgabe der App.

## Was die Integration übernimmt

| Aufgabe | Verhalten |
| --- | --- |
| **Auswahl der Entitäten** | Bevorzugt Labels; optional einzelne Entitäten, Bereiche, Geräte und Entity-Muster kombinieren |
| **Ausschlüsse** | Einzelne Entity-IDs und Ausschlussmuster haben immer Vorrang |
| **Wertaufbereitung** | Numerische Werte mit einstellbaren Nachkommastellen (0–3, Standard 3) sowie Schalter- (`on`/`off`) und Anwesenheitszustände (`home`/`not_home`) |
| **Zuverlässiger Transport** | In-Memory-Queue, Batches, Timeout und dauerhafte Retries |
| **Sichere Verbindung** | Bearer-Token; Reauth-Hinweis bei abgelehntem Token |
| **Diagnose** | Vier Diagnose-Sensoren und Diagnose-Download |
| **Filter übertragen** | Als versioniertes YAML exportieren/importieren — praktisch, um dieselbe Auswahl auf ein zweites System zu übernehmen |

## Installation

### Über HACS (empfohlen)

[![HACS-Repository in My Home Assistant öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bertel2020&repository=HA-Zeitarchiv&category=integration)
[![Zeitarchiv zu My Home Assistant hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=zeitarchiv)

1. Über den ersten Button das Zeitarchiv-Repository in HACS öffnen.
2. **Zeitarchiv** herunterladen und Home Assistant neu starten.
3. Über den zweiten Button die Integration hinzufügen. Alternativ in Home
   Assistant **Einstellungen → Geräte & Dienste → Integration hinzufügen →
   Zeitarchiv** öffnen.

Falls der erste Button nicht funktioniert, in HACS unter **Integrationen →
Benutzerdefinierte Repositories**
`https://github.com/bertel2020/HA-Zeitarchiv` als Kategorie **Integration**
eintragen.

### Manuell

#### 1. Voraussetzung

Die [Zeitarchiv-App](https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv) muss laufen. Den API-Token findest
du dort unter **Einstellungen → Verbindung**.

App und Integration versionieren unabhängig voneinander, keine bestimmte
Mindestversion nötig — neuere Funktionen (z. B. der Betriebsmodus-Sensor)
bleiben gegen eine ältere Gegenseite einfach ungenutzt, statt die
Verbindung zu stören.

#### 2. Custom Integration kopieren

Das Verzeichnis `custom_components/zeitarchiv` nach
`/config/custom_components/zeitarchiv` kopieren und Home Assistant neu
starten.

#### 3. Verbindung einrichten

In Home Assistant **Einstellungen → Geräte & Dienste → Integration hinzufügen
→ Zeitarchiv** öffnen und eintragen:

| Feld | Bedeutung |
| --- | --- |
| Verbindungsname | Frei wählbarer Name, z. B. `Produktivsystem` oder `Testsystem` |
| Host | Erreichbarer Host der Zeitarchiv-App |
| Port | Standardmäßig `8127` |
| API-Token | Token aus den App-Einstellungen |

Die Verbindung wird vor dem Speichern geprüft. Ein nicht erreichbarer Host und
ein abgelehnter Token erscheinen als getrennte Fehlermeldungen.

Mehrere Verbindungen können parallel eingerichtet werden. Jede Verbindung hat
eine eigene Warteschlange, eigene Filter und eigene Diagnose-Sensoren. Dadurch
kann derselbe Home Assistant seine Zustandsänderungen beispielsweise zugleich
an ein Produktiv- und ein Test-Zeitarchiv senden; auch zwei benannte Einträge
mit identischem Host und Port sind zulässig.

#### 4. Archivfilter wählen

Auf der Zeitarchiv-Integrationskachel **Konfigurieren → Archivfilter
bearbeiten** öffnen.

| Auswahl | Wirkung |
| --- | --- |
| Labels (empfohlen) | Direkt gelabelte Entitäten sowie Entitäten gelabelter Geräte und Bereiche; Änderungen gelten ohne erneutes Speichern für folgende Zustandsänderungen |
| Einzelne Entitäten | Zusätzliche konkrete Entity-IDs |
| Bereiche | Alle aktuell zugeordneten Entitäten |
| Geräte | Alle aktuell zugeordneten Entitäten |
| Ausgeschlossene Entitäten | Werden in jedem Fall verworfen |
| Entitätsmuster einschließen | `*`-/`?`-Muster; ohne Punkt für Objekt-IDs, mit Punkt für vollständige Entity-IDs |
| Entitätsmuster ausschließen | Musterbasierte Ausschlüsse mit demselben Vorrang wie einzelne Ausschlüsse |
| Nachkommastellen | Rundung numerischer Werte vor der Übertragung, 0–3, Standard 3 |

Nach dem Absenden zeigt ein Prüfschritt die tatsächlich aufgelösten
Entity-IDs. Die Vorschau unterscheidet aktive Entitäten, registrierte
Entitäten ohne aktuellen Zustand und durch Ausschlüsse entfernte Entitäten.
Bei Labels, Bereichen und Geräten werden dadurch alle zugehörigen Entitäten
sichtbar, bevor die Auswahl gespeichert wird. Die Vorschau nennt außerdem die
eingestellten Nachkommastellen; Schaltzustände werden unabhängig davon als
`1/0` gespeichert.

Über **Konfigurieren → Aktuell erfasste Entitäten** lässt sich derselbe Report
auch später jederzeit für die gespeicherten Filter öffnen, ohne die Auswahl zu
verändern.

Domainfilter werden nicht mehr angeboten. Beim Upgrade werden früher
gespeicherte Domainauswahlen einmalig in die zu diesem Zeitpunkt bekannten
konkreten Entity-IDs umgewandelt. Für neue und später hinzukommende Entitäten
sind Labels der bevorzugte Weg.

## Datenfluss

```text
Integration geladen/neu geladen ─► aktueller Zustand
state_changed                  ───► neue Zustandsänderung
     │
     ├─ nur tatsächliche Zustandsänderung?
     ├─ Filter trifft zu und nicht ausgeschlossen?
     └─ unterstützter Wert?
             │
             ▼
       In-Memory-Queue
       max. 5.000 Events
             │
             ▼
       Batch bis 100 Events
       oder spätestens nach 5 s
             │
             ▼
       Zeitarchiv-App :8127
```

Eine stabile Event-ID macht wiederholte Übertragungen idempotent. Geht eine
HTTP-Antwort verloren, kann derselbe Batch erneut gesendet werden, ohne in der
App denselben Messpunkt doppelt anzulegen.

Unmittelbar beim Laden oder Neuladen eines Integrationseintrags werden die
aktuellen Zustände aller passenden Entitäten einmal in die Warteschlange
gelegt. Dadurch erscheinen neu ausgewählte Entitäten sofort in der App; die
Integration wartet weder auf die nächste Zustandsänderung noch auf einen
erneuten Start von Home Assistant.

## Welche Werte werden archiviert?

Die Integration reagiert nur, wenn sich der eigentliche Zustand ändert. Eine
reine Änderung von Attributen wie Friendly Name oder Einheit erzeugt keinen
zusätzlichen Archivpunkt.

- Numerische Zustände von `sensor`, `climate`, `input_number`, `counter` und
  vergleichbaren Domains werden als Zahl mit den im Options-Flow eingestellten
  Nachkommastellen (0–3, Standard 3) übertragen. Empfohlen ist der Standard;
  weniger Nachkommastellen verbessern die Komprimierbarkeit der
  Langzeitspeicherung in der App und können bei sehr vielen Entitäten und
  langer Aufbewahrung spürbar Speicherplatz sparen, kosten bei kleinteiligen
  Messwerten (z. B. Strom in A) aber Genauigkeit.
- `binary_sensor`, `switch` und `input_boolean` werden als `on → 1` und
  `off → 0` übertragen.
- `device_tracker` und `person` werden als Anwesenheit übertragen:
  `home → 1`, jeder andere Zustand (`not_home` oder eine benannte Zone
  ungleich `home`) `→ 0`.
- Textwerte sowie `unknown`, `unavailable`, `none` und leere Zustände werden
  nicht archiviert.

Auflösung, Aufbewahrung und Bereinigungsschwellen gehören nicht in diesen
Filter. Sie werden global oder je Entität in der App konfiguriert.

## Einstellungsmenü

**Konfigurieren** öffnet ein kompaktes Menü mit vier Aktionen:

1. **Archivfilter bearbeiten** – aktive Auswahl ändern.
2. **Aktuell erfasste Entitäten** – aufgelöste Auswahl und Rundung prüfen.
3. **Filter als YAML exportieren** – eine portable Kopie anzeigen.
4. **Filter aus YAML importieren** – alle Filter aus einer Kopie ersetzen.

### YAML-Export für Testsysteme

Der Export enthält ausschließlich die Filter und niemals Host, Port oder
API-Token. Der angezeigte Inhalt kann kopiert und als `.yaml` gespeichert
werden:

```yaml
format: zeitarchiv-options
version: 3
filters:
  labels:
    - zeitarchiv
  entities:
    - sensor.aussentemperatur
  areas: []
  devices: []
  exclude_entities:
    - sensor.testwert
  entity_patterns:
    - sensor.wetter_*
  exclude_entity_patterns:
    - "*_id"
```

Der Import verwendet einen sicheren YAML-Loader und prüft Formatversion,
Struktur, Entity-IDs und Muster. Exporte der vorherigen Formatversionen 1 und 2
bleiben importierbar; enthaltene Domains werden einmalig in aktuell bekannte
Entity-IDs umgewandelt. Erst nach erfolgreicher Prüfung ersetzt der Import die
Optionen und lädt die Integration neu.

> [!NOTE]
> Entity-IDs sind zwischen gleich aufgebauten Systemen meist direkt
> übertragbar. Labels, Bereiche und Geräte referenzieren interne Registry-IDs
> und funktionieren auf dem Zielsystem nur, wenn diese IDs übereinstimmen.

## Warteschlange und Fehlerverhalten

| Eigenschaft | Wert |
| --- | ---: |
| Maximale Queue | 5.000 Events |
| Batchgröße | 100 Events |
| Batch-Timeout | 5 Sekunden |
| Retry-Abstände | 1, 2, 4, 8, 15, 30, danach 60 Sekunden |

Der Worker läuft in einem eigenen Thread und blockiert den Home-Assistant-
Event-Loop nicht. Ein fehlgeschlagener Batch bleibt erhalten und wird ohne
festes Retry-Limit erneut versucht. Beim Entladen versucht die Integration,
Queue und Teilbatch kontrolliert zu leeren.

Ist die Queue voll, werden neu eintreffende Events verworfen und gezählt. Die
Queue ist nicht persistent; ein Neustart verwirft noch nicht übertragene
Werte.

## Diagnose in Home Assistant

Auf der Geräteseite der Integration erscheinen unter **Diagnose** vier
Sensoren:

| Sensor | Aussage |
| --- | --- |
| Letzte Übertragung | Zeitpunkt des letzten bestätigten Batches |
| Übertragene Datensätze (seit Start) | Von der App bestätigte Events; Retries zählen nicht doppelt |
| Warteschlange | Noch wartende Events im Hintergrund-Worker |
| Verworfene Ereignisse (seit Start) | Wegen voller oder gestoppter Queue verworfene Events |

Die beiden Zähler beginnen nach jedem Start der Integration bei null.

Über die Integrationskachel kann zusätzlich **Diagnose herunterladen** gewählt
werden. Der Bericht enthält:

- einen aktuellen Verbindungstest;
- Queue-Größe, letzten Fehler und letzten Erfolg;
- gesendete und verworfene Events seit Start;
- Zahl der momentan von den Filtern erfassten Entitäten;
- die gespeicherten Optionen.

Der API-Token wird automatisch geschwärzt.

## Wartungshinweise: Repairs und Health-Sensoren

Beide Wege lesen dieselben Meldungen der App (`/api/notices`, gepollt alle
60 s), aber für unterschiedliche Zwecke — nur ein Ausschnitt wird zur
Repair-Karte, ein anderer (überlappender) Ausschnitt zu automatisierbaren
Entities:

**Drei `binary_sensor`-Health-Entities** am Zeitarchiv-Gerät, bewusst
**keine** Diagnose-Entities (sollen im normalen Dashboard/für Automationen
auffindbar bleiben):

| Sensor | Springt an bei |
| --- | --- |
| Backup fehlgeschlagen | letzter Sicherungslauf fehlgeschlagen |
| Inaktive Entitäten erkannt | eine oder mehrere Entitäten melden sich seit mehreren Tagen nicht mehr (info/warn/error gebündelt) |
| Wartungshinweis | Speicherindex-Abgleichsfehler, fehlgeschlagene Aufbewahrung, empfohlene Bereinigung, knapper Host-Speicherplatz, empfohlene Index-Optimierung |
| Hintergrunddienst reagiert nicht | Wartungsplaner, Speicherindex-Abgleich oder laufendes Backup melden seit mehreren Minuten keinen Fortschritt mehr — anders als „Backup fehlgeschlagen" erkennt das auch einen hängenden statt nur einen fehlgeschlagenen Lauf |

Jeder Sensor trägt als Attribut `reasons`/`details` die genauen Meldungs-IDs
und Texte, die ihn gerade auslösen — praktisch, wenn mehrere Ursachen
gleichzeitig zutreffen.

**Home-Assistant-Repairs** (Einstellungen → System → Repairs) decken davon
nur die wirklich kritischen Fälle ab, die einer bewussten Reaktion
bedürfen: fehlgeschlagenes Backup, fehlgeschlagene Aufbewahrung, lange
inaktive Entitäten (nur die kritische Stufe), veraltete
Integrationsversion, sowie kritisch knapper Host-Speicherplatz. Absichtlich
keine interaktiven Fix-Flows — die eigentliche Behebung (Backup erneut
anstoßen, Aufbewahrung prüfen, Integration aktualisieren) passiert in der
Zeitarchiv-App bzw. über HACS, die Repair-Karte dient als Hinweis mit
Handlungsanweisung im Text.

**Eine Ausnahme kommt nicht aus den Meldungen:** Das Repair-Issue „Zeitarchiv-
Verbindung pausiert" (siehe [Token ändern](#token-ändern)) entsteht
eigenständig direkt aus dem Schreibpfad, weil der normale, meldungsbasierte
Weg in genau dem Moment (abgelehnter Token) selbst nicht erreichbar ist.

## Betriebsmodus

Der Sensor **Betriebsmodus** am Zeitarchiv-Gerät zeigt, ob die verbundene
App-Instanz gerade produktiv oder im Demo-Modus läuft (eine synthetische
Vorführ-/Testinstanz mit eigenem Datenverzeichnis, siehe Zeitarchiv-App-
Dokumentation). Nützlich, um in Automationen oder per Blick aufs Dashboard
zu erkennen, ob man gerade auf einer Vorführinstanz statt der echten Anlage
sitzt. Bewusst keine Diagnose-Entity, aus demselben Grund wie beim
Backup-Sensor unten. Ist die App gerade nicht erreichbar, zeigt die Entity
den Home-Assistant-Standardzustand „Nicht verfügbar" statt eines falschen
Werts.

## Offsite-Backup per Automation

Zeitarchiv spricht selbst kein S3/WebDAV/SMB — dafür bräuchte der Container
neue Abhängigkeiten und Zugangsdaten, für einen Fall, den der HA-Host ohnehin
besser löst. Stattdessen liefert die Integration einen Automations-Trigger:
den Sensor **Letztes Backup** (State = Zeitstempel des letzten
ERFOLGREICHEN Backups, Attribute `filename`/`size_bytes`) — bewusst keine
Diagnose-Entity, damit er in Automationen leicht auffindbar bleibt.

[![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fbertel2020%2FHA-Zeitarchiv%2Fmain%2Fblueprints%2Fautomation%2Fzeitarchiv%2Fbackup_upload.yaml)

Nach dem Import: den Backup-Sensor der gewünschten Verbindung auswählen und
eine eigene Upload-Aktion eintragen, z. B. ein `shell_command` mit
`rclone copy`:

```yaml
shell_command:
  rclone_backup_upload: "rclone copy '/config/zeitarchiv-backups/{{ filename }}' remote:zeitarchiv-backups/"
```

In der Blueprint-Aktion stehen Dateiname und Größe per Vorlage zur
Verfügung: `{{ trigger.to_state.attributes.filename }}` und
`{{ trigger.to_state.attributes.size_bytes }}`.

## Token ändern

Wird der Token in der App neu generiert, lehnt die App den nächsten Batch ab.
Die Integration startet daraufhin den Home-Assistant-Reauth-Flow; der
ausstehende Batch bleibt erhalten. Den neuen Token einfach im angezeigten
Dialog eintragen.

**Ausnahme: Demo-Modus.** Schaltet die App auf den [Demo-Modus](#betriebsmodus)
um, ändert sich ihr Token ebenfalls — löst aber bewusst **keinen** Reauth
aus: Die Integration erkennt den Grund selbst (kein echtes Tokenproblem) und
pausiert stattdessen ruhig, erkennbar an einem eigenen Hinweis unter
Einstellungen → Repairs. Sobald die App zurück auf Produktiv geschaltet
wird, sendet die Verbindung von selbst wieder — mit dem ursprünglichen
Token, ohne etwas hier nachzupflegen. Nur wenn sich das nicht eindeutig
bestimmen lässt, fragt der gewohnte Reauth-Dialog nach — und warnt dann
zusätzlich, falls der neu eingetragene Token zufällig doch zu einer
Demo-Instanz gehört.

Verbindungsname, Host, Port und Token können außerdem jederzeit über die
Integrationskachel → **Neu konfigurieren** geändert werden. Die Verbindung wird
vor der Übernahme erneut getestet.

## Filterlogik im Detail

Eine Entität wird archiviert, wenn sie nicht ausdrücklich ausgeschlossen ist
und mindestens eine Einschlussregel erfüllt:

```text
nicht ausgeschlossen
        UND
(Domain gewählt ODER Entity-ID gewählt ODER über Bereich/Gerät aufgelöst
 ODER Einschlussmuster trifft)
```

Muster ohne Punkt werden auf die Objekt-ID hinter der Domain angewendet:
`*_id` trifft beispielsweise `sensor.device_id` und `input_number.user_id`.
Muster mit Punkt prüfen die vollständige Entity-ID, sodass `sensor.*_id` nur
Sensoren erfasst. Unterstützt werden ausschließlich `*` und `?`; reguläre
Ausdrücke sind bewusst nicht zugelassen.

Bereiche und Geräte werden beim Speichern der Optionen in konkrete Entity-IDs
aufgelöst. Entitäten, die später neu zu einem gewählten Bereich oder Gerät
hinzukommen, werden erst nach erneutem Speichern der Filter berücksichtigt.

## Bekannte Grenzen

- Nichtnumerische Textsensoren werden nicht archiviert.
- Bereichs- und Gerätezuordnungen werden nicht laufend neu aufgelöst.
- Queue und Übertragungszähler bestehen nur für die Laufzeit der Integration.
- Die Verbindung verwendet einen gemeinsamen statischen Token und kein OAuth.
- Die Integration ist ein Schreibpfad; archivierte Werte werden nicht als neue
  Home-Assistant-Entitäten zurückgelesen.

---

<p align="center">
  <a href="https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv">Zeitarchiv-App</a>
  ·
  <a href="https://github.com/bertel2020/HA-Apps/blob/main/zeitarchiv/CHANGELOG.md">App-Changelog</a>
</p>

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
Copyright 2026 Roberto / bertel2020.
