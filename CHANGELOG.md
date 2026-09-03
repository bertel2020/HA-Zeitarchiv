# Changelog

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
