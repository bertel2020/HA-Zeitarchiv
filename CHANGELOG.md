# Changelog

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
