<p align="center">
  <img src="custom_components/zeitarchiv/brand/logo.png" alt="Zeitarchiv" width="160">
</p>

<h1 align="center">Zeitarchiv Integration</h1>

<p align="center">
  Der zuverlässige Schreibpfad von Home Assistant in das Zeitarchiv.<br>
  <sub>FILTER · QUEUE · BATCHING · RETRY · DIAGNOSE · YAML-TRANSFER</sub>
</p>

Die Zeitarchiv-Integration beobachtet ausgewählte Zustandsänderungen und
überträgt sie gebündelt an die [Zeitarchiv-App](https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv). Sie
erzeugt keine Kopien der archivierten Entitäten in Home Assistant: Die
eigentlichen Zeitreihen, Charts und Tabellen bleiben Aufgabe der App.

## Was die Integration übernimmt

| Aufgabe | Verhalten |
| --- | --- |
| Auswahl | Domains, einzelne Entitäten, Bereiche, Geräte und Entity-Muster kombinieren |
| Ausschluss | Einzelne Entity-IDs und Ausschlussmuster haben immer Vorrang |
| Aufbereitung | Numerische Werte mit maximal drei Nachkommastellen sowie Schalterzustände `on`/`off` |
| Transport | In-Memory-Queue, Batches, Timeout und dauerhafte Retries |
| Sicherheit | Bearer-Token; Reauth-Hinweis bei abgelehntem Token |
| Transparenz | Vier Diagnose-Sensoren und Diagnose-Download |
| Übertragbarkeit | Filter als versioniertes YAML exportieren/importieren |

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

## Installation

### Über HACS

1. In HACS **Integrationen** öffnen.
2. Über das Menü **Benutzerdefinierte Repositories** auswählen.
3. `https://github.com/bertel2020/HA-Zeitarchiv` eintragen und als Kategorie
   **Integration** wählen.
4. **Zeitarchiv** herunterladen und Home Assistant neu starten.

### Manuell

#### 1. Voraussetzung

Die [Zeitarchiv-App](https://github.com/bertel2020/HA-Apps/tree/main/zeitarchiv) muss laufen. Den API-Token findest
du dort unter **Einstellungen → Verbindung**.

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
| Domains | Alle passenden Entitäten dieser Domain |
| Einzelne Entitäten | Zusätzliche Entity-IDs, unabhängig von der Domain |
| Bereiche | Alle beim Speichern zugeordneten Entitäten |
| Geräte | Alle beim Speichern zugeordneten Entitäten |
| Ausgeschlossene Entitäten | Werden in jedem Fall verworfen |
| Entitätsmuster einschließen | `*`-/`?`-Muster; ohne Punkt für Objekt-IDs, mit Punkt für vollständige Entity-IDs |
| Entitätsmuster ausschließen | Musterbasierte Ausschlüsse mit demselben Vorrang wie einzelne Ausschlüsse |

Nach dem Absenden zeigt ein Prüfschritt die tatsächlich aufgelösten
Entity-IDs. Die Vorschau unterscheidet aktive Entitäten, registrierte
Entitäten ohne aktuellen Zustand und durch Ausschlüsse entfernte Entitäten.
Bei Bereichen und Geräten werden dadurch alle zugehörigen Entitäten sichtbar,
bevor die Auswahl gespeichert wird.

Über **Konfigurieren → Aktuell erfasste Entitäten** lässt sich derselbe Report
auch später jederzeit für die gespeicherten Filter öffnen, ohne die Auswahl zu
verändern.

Beim ersten Öffnen sind `sensor`, `binary_sensor`, `switch`, `climate`,
`input_number`, `input_boolean` und `counter` vorausgewählt. Bereits
gespeicherte Auswahlen werden dadurch nicht verändert.

## Welche Werte werden archiviert?

Die Integration reagiert nur, wenn sich der eigentliche Zustand ändert. Eine
reine Änderung von Attributen wie Friendly Name oder Einheit erzeugt keinen
zusätzlichen Archivpunkt.

- Numerische Zustände von `sensor`, `climate`, `input_number`, `counter` und
  vergleichbaren Domains werden als Zahl mit maximal drei Nachkommastellen
  übertragen.
- `binary_sensor`, `switch` und `input_boolean` werden als `on → 1` und
  `off → 0` übertragen.
- Textwerte sowie `unknown`, `unavailable`, `none` und leere Zustände werden
  nicht archiviert.

Auflösung, Aufbewahrung, Rundung und Bereinigungsschwellen gehören nicht in
diesen Filter. Sie werden global oder je Entität in der App konfiguriert.

## Einstellungsmenü

**Konfigurieren** öffnet ein kompaktes Menü mit drei Aktionen:

1. **Archivfilter bearbeiten** – aktive Auswahl ändern.
2. **Filter als YAML exportieren** – eine portable Kopie anzeigen.
3. **Filter aus YAML importieren** – alle Filter aus einer Kopie ersetzen.

### YAML-Export für Testsysteme

Der Export enthält ausschließlich die Filter und niemals Host, Port oder
API-Token. Der angezeigte Inhalt kann kopiert und als `.yaml` gespeichert
werden:

```yaml
format: zeitarchiv-options
version: 2
filters:
  domains:
    - binary_sensor
    - sensor
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
Struktur, Domains, Entity-IDs und Muster. Exporte der vorherigen Formatversion
1 bleiben importierbar. Erst nach erfolgreicher Prüfung ersetzt der Import die
Optionen und lädt die Integration neu.

> [!NOTE]
> Entity-IDs sind zwischen gleich aufgebauten Systemen meist direkt
> übertragbar. Bereiche und Geräte referenzieren interne Registry-IDs und
> funktionieren auf dem Zielsystem nur, wenn diese IDs übereinstimmen.

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

## Token ändern

Wird der Token in der App neu generiert, lehnt die App den nächsten Batch ab.
Die Integration startet daraufhin den Home-Assistant-Reauth-Flow; der
ausstehende Batch bleibt erhalten. Den neuen Token einfach im angezeigten
Dialog eintragen.

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

## Entwicklung

HACS und Home Assistants `hassfest` prüfen die Repository- und
Integrationsstruktur automatisch bei jedem Push und Pull Request.

Relevante Module:

| Datei | Aufgabe |
| --- | --- |
| `config_flow.py` | Einrichtung, Reauth, Filtermenü und YAML-Transfer |
| `events.py` | Validierung und Event-Aufbereitung |
| `filtering.py` | Ein- und Ausschlusslogik |
| `queue_writer.py` | Queue, Batching, Retry und Live-Zähler |
| `sensor.py` | Diagnose-Entitäten |
| `diagnostics.py` | Geschwärzter Diagnosebericht |

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

Dieses Projekt steht unter der [Apache License 2.0](LICENSE).
Copyright 2026 Roberto / bertel2020.
