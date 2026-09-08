"""Regressionstests für die Coordinator-Datenform nach Roadmap 1.4:
ZeitarchivNoticesCoordinator.data ist seitdem {"notices": [...],
"latest_backup": {...} | None} statt einer bloßen Liste.

coordinator.py, binary_sensor.py, sensor.py und __init__.py importieren
`homeassistant`, das in dieser Testumgebung nicht installiert ist (siehe
_pkg.py-Docstring) — deshalb hier reine Quelltext-Prüfungen statt eines
echten Imports/einer Instanziierung, nach dem etablierten Muster von
test_config_flow_sortable_entities.py. Bewusst kein Ersatz für einen
Verhaltenstest, sondern eine bekannte Lücke: ohne homeassistant-Stubs (die
es in diesem Repo nirgends gibt) ist mehr hier nicht möglich."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def test_coordinator_declares_dict_data_type() -> None:
    source = (INTEGRATION_DIR / "coordinator.py").read_text(encoding="utf-8")
    assert "DataUpdateCoordinator[dict]" in source
    assert "DataUpdateCoordinator[list[dict]]" not in source


def test_binary_sensor_reads_notices_key_from_dict_shaped_coordinator_data() -> None:
    source = (INTEGRATION_DIR / "binary_sensor.py").read_text(encoding="utf-8")
    assert '.get("notices", [])' in source
    assert "self.coordinator.data or []" not in source


def test_init_repairs_sync_reads_notices_key_from_dict_shaped_coordinator_data() -> None:
    source = (INTEGRATION_DIR / "__init__.py").read_text(encoding="utf-8")
    assert '.get("notices", [])' in source
    assert "notices_coordinator.data or []" not in source


def test_sensor_defines_latest_backup_sensor_without_diagnostic_category() -> None:
    source = (INTEGRATION_DIR / "sensor.py").read_text(encoding="utf-8")
    start = source.index("class ZeitarchivLatestBackupSensor")
    rest = source[start:]
    end = rest.find("\nclass ", 1)
    class_source = rest if end == -1 else rest[:end]

    assert "SensorDeviceClass.TIMESTAMP" in class_source
    assert "_attr_entity_category" not in class_source


def test_entity_sensor_translations_have_latest_backup_key() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        assert "name" in data["entity"]["sensor"]["latest_backup"]
