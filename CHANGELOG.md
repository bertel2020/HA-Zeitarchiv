# Changelog

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
