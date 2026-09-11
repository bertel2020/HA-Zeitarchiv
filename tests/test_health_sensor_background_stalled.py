"""Regressionstests für den neuen Health-binary_sensor "background_stalled"
und die Erweiterung von "health_issue" um system.index_optimization.

Anders als backup_failed (reagiert erst, wenn ein Job den Endzustand
"failed" erreicht): ein hängender Hintergrund-Thread erreicht diesen
Endzustand nie und blieb bisher komplett unsichtbar — deckt die drei
*_stalled-Meldungen der App ab (Wartungsplaner, Speicherindex-Abgleich,
laufendes Backup). binary_sensor.py importiert homeassistant, das in dieser
Testumgebung nicht installiert ist (siehe _pkg.py-Docstring) — deshalb reine
Quelltext-Prüfungen nach dem etablierten Muster von
test_notices_coordinator_backup_shape.py."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def test_binary_sensor_declares_background_stalled_spec_with_all_three_notice_ids() -> None:
    source = (INTEGRATION_DIR / "binary_sensor.py").read_text(encoding="utf-8")
    assert '"background_stalled"' in source
    for notice_id in (
        "system.scheduler_stalled",
        "system.storage_reconcile_stalled",
        "system.backup_worker_stalled",
    ):
        assert f'"{notice_id}"' in source


def test_binary_sensor_health_issue_spec_includes_index_optimization() -> None:
    source = (INTEGRATION_DIR / "binary_sensor.py").read_text(encoding="utf-8")
    start = source.index('"health_issue"')
    end = source.index(")", start)
    spec_source = source[start:end]
    assert '"system.index_optimization"' in spec_source


def test_entity_binary_sensor_translations_have_background_stalled_key() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        assert "name" in data["entity"]["binary_sensor"]["background_stalled"]
