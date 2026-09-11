"""Regressionstest: der Health-binary_sensor "health_issue" (Wartungshinweis)
deckt seit der Bestandsaufnahme des App-Meldungskatalogs (app/notices.py)
zusätzlich system.index_optimization ab — ein wiederkehrendes, aber
unkritisches Housekeeping-Signal (Index-Datei sollte VACUUMt werden), das
gut zu den bereits dort gebündelten Speicherplatz-/Aufbewahrungshinweisen
passt. Ein separater Sensor für die drei *_stalled-Meldungen
(Wartungsplaner/Speicherindex-Abgleich/Backup hängen) wurde in derselben
Bestandsaufnahme vorgeschlagen, aber wieder verworfen — kein Codeeingriff
dafür.

binary_sensor.py importiert homeassistant, das in dieser Testumgebung
nicht installiert ist (siehe _pkg.py-Docstring) — deshalb eine reine
Quelltext-Prüfung nach dem etablierten Muster von
test_notices_coordinator_backup_shape.py."""

from __future__ import annotations

from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def test_binary_sensor_health_issue_spec_includes_index_optimization() -> None:
    source = (INTEGRATION_DIR / "binary_sensor.py").read_text(encoding="utf-8")
    start = source.index('"health_issue"')
    end = source.index(")", start)
    spec_source = source[start:end]
    assert '"system.index_optimization"' in spec_source
