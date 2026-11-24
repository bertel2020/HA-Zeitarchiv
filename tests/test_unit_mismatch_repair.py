"""Repair-Karte für ``entities.unit_mismatch`` (App-Roadmap 1.3).

Reine Quelltext-Prüfung, weil `homeassistant` in dieser Testumgebung nicht
installiert ist; der Ablauf mit Home Assistant steht in tests/ha/test_notices.py."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def _always_ids() -> str:
    source = (INTEGRATION_DIR / "repairs.py").read_text(encoding="utf-8")
    start = source.index("_ALWAYS_IDS = frozenset({")
    return source[start:source.index("})", start)]


def test_unit_mismatch_becomes_a_repair_but_the_info_notice_does_not() -> None:
    ids = _always_ids()
    assert '"entities.unit_mismatch"' in ids
    # Umgerechnete Werte sind unkritisch und bleiben in der App.
    assert '"entities.unit_converted"' not in ids


def test_the_repair_has_a_title_and_description_in_every_language_file() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        issue = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))["issues"]["entities_unit_mismatch"]
        assert issue["title"] and "{connection}" in issue["description"] and "{detail}" in issue["description"], name
