# Changelog (Deutsch)

> English version: [CHANGELOG.md](CHANGELOG.md)

## Unreleased

### Geändert

- **Dokumentation**: Klarere Installation
  - Die README sagt jetzt gleich am Anfang, dass die Integration die
    Zeitarchiv-App braucht, die getrennt über den App-Store und nicht über
    HACS installiert wird
  - Button zum Hinzufügen des App-Repositorys und die Schritte bis zum API-Token

## 1.5.0 - 2026-11-10

### Neu

- **Karte: Legende**: Die Legende der Chart-Karte lässt sich ausschalten und
  in zwei Größen zeigen
  - Legenden-Stil „Aus“ blendet die Legende ganz aus
  - Legendengröße „Wie im Chart“, „Normal“ oder „Klein“; ohne Angabe gilt die
    Größe des Charts
- **Karte: Weitere Sensoren nach Raum und Etage**: Die Tabelle des
  Wetterdashboards gruppiert die Sensoren nach Raum, die Räume lassen sich
  einklappen und stehen unter ihrer Etage aus Home Assistant (braucht
  Zeitarchiv 1.40.0)
- **Karte: Tabellen**: Die Karte folgt den Tabellen der App
  - Neue Zeilen-Aggregation „Aktueller Wert“, Nachkommastellen der Entität bei
    der Spalte „Auto“
  - Spalten „Heute“ und „Gestern“, Vorjahr-Menü und Spaltenköpfe wie in der
    App, einzelne Jahre mit eigenem Kopf
- **Karte: Charts**: Anpassungen an die App
  - Der Monatsvergleich zeigt höchstens die letzten fünf früheren Jahre, alle
    stehen in der Legende, ältere Jahre blasser
  - Monatsdiagramm mit wählbaren Nachkommastellen
  - Neue Kenntage „Tage ohne Netzbezug“ und „Hohe Einspeisung“, Jahre ohne
    Speicher; Heatmap mit Farbverlauf und Text für leere Felder, der 29.
    Februar in der Jahresmatrix grau
  - Rekorde ohne Mindestlänge des Archivs, mit eigenem Text, wenn noch keine
    vorliegen

## 1.4.2 - 2026-11-08

### Behoben

- **Karte: Datumsauswahl der Energie**: Die Karte folgt dem Datum auch nach
  einem Ansichtswechsel oder dem Bearbeitungsmodus
  - „Diese Woche“ zeigte ab dem vierten Wochentag die Vorwoche
- **Karte: Editor**: Die Einstellungen eines Bausteins (Zeitraum, Rolle, Werte)
  gehen nicht mehr verloren, wenn die Liste der Bausteine nicht geladen werden
  konnte
- **Karte: Tabellen**: Ein Ladefehler erscheint als Fehler statt als leere
  Zellen; die Legende eines vorherigen Charts bleibt nicht mehr unter einer
  Tabelle stehen
- **Karte: Legende**: Nach dem Umschalten eines Eintrags per Tastatur bleibt der
  Fokus erhalten; beim Jahresvergleich gilt das Vorjahr bis zum gleichen Tag
  und das Jahr stimmt auch bei abweichender Zeitzone des Browsers
- **Karte: Dashboard-Bausteine**: Wer kein Administrator ist, sieht den Hinweis,
  dass Bausteine nur Administratoren sehen, statt eines Hinweises auf „Karte
  freigeben“

## 1.4.1 - 2026-11-05

### Geändert

- **Karte: Editor bei Dashboard-Bausteinen**: Die Felder eines Bausteins heißen
  jetzt „Spalten“, „Mit Vorjahr vergleichen“, „Differenz anzeigen“ und so weiter
  statt „columns“, „vorjahr“ und „diff“
  - Kurze Hinweise erklären, was Vorjahr, Differenz, Perioden zurück und die
    Datumsauswahl der Energie bewirken
  - Der Titel nennt als Vorgabe den Namen des Bausteins, bei einer Tabelle den
    der Tabelle
  - Aktualisierung, Höhe und Tippen stehen unter „Weitere Einstellungen“
    eingeklappt, bei allen Quellen der Karte; Aktualisierung und Höhe nennen
    ihren Standard, wenn das Feld leer ist
  - Unter dem Baustein steht ein Satz, was er zeigt
  - Zeitraum, Perioden zurück und die Datumsauswahl der Energie stehen
    zusammen in einem eigenen Abschnitt, Stil und Kennzahlen der Legende
    eingeklappt unter „Legende anpassen“
- **Karte: Beschreibung**: Im Dialog zum Hinzufügen nennt die Karte jetzt auch
  Tabellen und Dashboard-Bausteine

### Behoben

- **Karte: Legende bei einer einzelnen Serie**: „Legende anzeigen“ wirkt jetzt
  auch bei einem Chart mit nur einer Entität. Ohne Angabe bleibt es wie bisher
  ohne Legende
- **Karte: Legende mit Werten bei einem Chart**: Die Chips standen ohne Abstände
  und Rahmen hintereinander („WirkleistungAktuell 574,8 WMin …“), wenn die Karte
  nur ein Chart zeigte. Jetzt sehen sie aus wie auf der Kachel der App

## 1.4.0 - 2026-11-05

### Neu

- **Karte: Dashboard-Bausteine**: Neue Quelle „Dashboard-Baustein“ im
  Karten-Editor. Die Karte zeigt Zeiträume im Vergleich aus dem Energie- und dem
  Wetterdashboard, Jahre × Monate aus der Energie sowie den Monatsvergleich
  (Energie, Wetter), die Jahresübersicht des Wetters, die Anteile und das
  Tageslastprofil der Energie als Diagramm sowie Kennzahlen-Kacheln aus Energie
  und Wetter, mit den Zahlen der App.
  - Im Editor lassen sich Spalten, Vorjahr und Differenz, bei der Matrix und dem
    Monatsvergleich Wert und Jahre, beim Wetter Gruppe oder Kennzahl, bei
    Anteilen, Lastprofil und Energie-Kennzahlen Zeitraum und Versatz, bei den
    Kennzahlen die Werte und den Verlauf wählen
  - Die Energie-Kennzahlen bieten zusätzlich Autarkie, Eigenverbrauch und den
    Speicher an; ohne Auswahl bleiben es die vier Energiemengen
  - Neu ist eine größere Speicher-Karte mit Batterie-Symbol und, bei einem Tag,
    der Kurve des Ladestands
  - Aus dem Langzeit der Energie kommen Rekorde, Kenntage je Jahr und „Was hat
    sich verändert?“ dazu; bei den Kenntagen wählt man Jahre und „bis heute“ oder
    ganze Jahre, bei den Veränderungen die Zahl der Verbraucher
  - Optional folgen Anteile und Lastprofil der Datumsauswahl des
    Energie-Dashboards von Home Assistant; ohne sie gilt der Zeitraum der Karte
  - Nur Administratoren sehen Bausteine; ist ein Baustein in der App nicht
    eingerichtet, sagt die Karte es
  - Braucht die aktuelle App; mit einer älteren meldet die Karte, dass die App
    zu alt ist

- **Karte: Legende mit Werten**: Die Karte zeigt unter dem Chart wie die
  Dashboard-Kachel der App Chips oder eine Tabelle mit Aktuell, Min, Max,
  Durchschnitt und Summe. Ein Klick auf einen Eintrag blendet die Serie ein oder
  aus.
  - Im Karten-Editor lassen sich Stil und Kennzahlen unter „Legende anzeigen“
    wählen; leer heißt wie im Chart
  - Auf einer schmalen Karte zeigt „Wie im Chart“ Chips statt einer Tabelle
  - Die Legende mit Werten braucht die aktuelle App; mit einer älteren bleibt es
    bei der Legende mit Namen

## 1.3.3 - 2026-11-03

### Behoben

- **Nichts geht beim Herunterfahren oder Neuladen verloren**: Waren Zustände
  noch nicht an die App übertragen, etwa weil sie nicht erreichbar war, gingen
  sie bei einem Neustart von Home Assistant oder beim Neuladen der Integration
  verloren. Sie werden jetzt gesichert und beim nächsten Start nachgesendet.

- **Reauth bei abgelehntem Token**: Der Hinweis zur erneuten Anmeldung erscheint
  jetzt auch, wenn gerade nichts zu schreiben ist.

- **Karte, Tastatur und Aufräumen**: Enter oder Leertaste auf einem
  Legendeneintrag löst nicht mehr die Tippaktion der Karte aus und schaltet
  die Serie wie gewohnt um. Wird die Karte entfernt, während Daten laden,
  zeichnet sie nicht mehr ins Leere. Jahres-, Monats- und Tagesgrenzen folgen
  der Zeitzone des Servers.

### Geändert

- **Geringere Last**: Zustandsänderungen werden im Event-Loop gefiltert statt im
  Thread-Pool, und der Stand „zuletzt gesendet“ wird seltener geschrieben (schont
  SD-Karten).

- **KI-Zugriff, Benutzerkonten**: Wer sich mit einem Konto ohne
  Administratorrechte verbindet (zum Beispiel ein Familienkonto), bekommt die
  Werkzeuge für einzelne Entitäten nicht mehr angeboten, wie bei der Karte.
  Energieübersicht und Meldungen stehen weiter zur Verfügung. Administratoren
  und der lokale Gesprächsagent von Home Assistant sind nicht betroffen.

## 1.3.2 - 2026-11-01

### Behoben

- **Zeitarchiv-Karte unter Home Assistant 2026.10**: Die Karte fehlte im
  Kartenwähler und im Dashboard oder erschien nur zufällig (Konsole: „Custom
  element not found: zeitarchiv-card“), je nach Browser und Ladezeitpunkt. Die
  Ursache liegt im Frontend von Home Assistant 2026.10 und ist ab 2026.11
  behoben. Die Karte und die Sparkline melden sich jetzt nach dem Start der App
  bei Bedarf noch einmal an und funktionieren damit auch unter 2026.10.

## 1.3.1 - 2026-11-01

### Behoben

- **Zeitarchiv-Karte, Wh und kWh**: Serien in Wh und kWh im selben Chart landeten
  auf zwei getrennten Achsen mit eigener Skala und waren nicht vergleichbar. Sie
  teilen sich jetzt eine Achse in der größten vorkommenden Einheit; reine
  Wh-Charts bleiben in Wh.
- **Zeitarchiv-Karte**: Die Dateien der Karte werden nicht mehr bis zu 31 Tage
  im Browser zwischengespeichert. Nach einem Update bleibt dadurch seltener
  eine alte Kartenversion hängen, die im Kartenwähler nur einen Ladekreis
  zeigt. In der Dokumentation steht jetzt, was in dem Fall zu tun ist.

## 1.3.0 - 2026-10-31

### Neu

- **Zeitarchiv-Karte für Lovelace** (`custom:zeitarchiv-card`, braucht
  die Zeitarchiv-App ab 1.12.0): Zeigt ein gespeichertes
  Chart oder eine gespeicherte Tabelle des Zeitarchivs direkt im Dashboard, im
  Hell- und Dunkelmodus und mit den Beschriftungen der Home-Assistant-Sprache.
  Die Karte lässt sich im Karteneditor einrichten; im Kartenwähler zeigt sie
  schon eine Vorschau mit deinem ersten Chart. Im Abschnitts-Layout nimmt sie
  die volle Breite und ihre Höhe selbst. Screenreader lesen zu jedem Diagramm
  Namen und Werte vor. Beim Tippen führt die Karte auf Wunsch eine Aktion von
  Home Assistant aus, zum Beispiel ein anderes Dashboard öffnen. Zuerst die App
  aktualisieren, dann die Integration.
  - **Für alle Benutzer freigeben**: Standardmäßig sehen nur Administratoren die
    Karte. In den Einstellungen der Integration unter **Karte freigeben**
    wählst du Charts und Tabellen, die jeder angemeldete Benutzer sieht, zum
    Beispiel auf einem Wandtablet. Entitäten direkt bleiben Administratoren
    vorbehalten.
  - **Entitäten direkt**: Statt eines gespeicherten Charts lassen sich bis zu
    zehn archivierte Entitäten mit Zeitraum und Darstellung wählen.
  - **Darstellungen**: Linien, Balken, gestapelt und in Prozent, Vergleich mit
    Vorperiode oder Vorjahr, Zeitstrahl, Zustände, Heatmap und Donut.
  - **Ausfälle**: Ist die App nicht erreichbar, zeigt die Karte den letzten
    Stand mit Hinweis und versucht es mit wachsendem Abstand erneut.
- **Sparkline für Kachelkarten**: Als zusätzliche Funktion der normalen
  Home-Assistant-Kachelkarte zeigt eine kleine Sparkline den Verlauf einer
  archivierten Zahlen-Entität (24 Stunden, 7 oder 30 Tage). Sie ist für alle
  Benutzer sichtbar.

## 1.2.1 - 2026-10-25

### Behoben

- **Thermostate fehlten bei Auswahl über Label, Gerät oder Bereich**:
  Heizkörperthermostate und andere Klimageräte (`climate`) werden jetzt auch
  dann archiviert, wenn du sie über ein Label, ein Gerät, einen Bereich oder
  ein Muster auswählst. Ihr Zustand (z. B. „heat“, „auto“, „off“) ist Text und
  wurde bisher nur bei Einzelauswahl übernommen. Andere Textentitäten
  erfasst weiterhin nur die Einzelauswahl.

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

## 1.0.0 - 2026-10-19

### Geändert

- Neues Icon und Logo, passend zum neuen Logo der Zeitarchiv-App.

### Behoben

- Lehnte die App ein einzelnes Ereignis ab, etwa wegen eines Texts mit mehr
  als 255 Zeichen, blieb die ganze Übertragung daran hängen: Die
  Warteschlange lief voll, und neue Zustandsänderungen aller Entitäten gingen
  verloren. Überlange Texte werden jetzt gekürzt, und ein abgelehnter Batch
  wird verworfen, statt die übrigen aufzuhalten.

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

## 0.19.0 - 2026-10-07

### Neu

- Die Integration übermittelt die Sprache von Home Assistant an die
  Zeitarchiv-App (Header `Accept-Language`). Fehlermeldungen der App
  erscheinen dadurch in der Sprache deiner Home-Assistant-Installation
  (Deutsch oder Englisch).

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
