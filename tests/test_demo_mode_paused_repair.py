"""Regressionstests für das eigenständige "demo_mode_paused"-Repair-Issue
(DEMO_MODUS_REAUTH_PLAN.md).

repairs.py und __init__.py importieren `homeassistant`, das in dieser
Testumgebung nicht installiert ist (siehe test_notices_coordinator_backup_
shape.py-Docstring) — deshalb hier reine Quelltext-Prüfungen statt eines
echten Imports/einer Instanziierung, nach demselben etablierten Muster."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def test_repairs_defines_a_standalone_demo_mode_paused_issue() -> None:
    """NICHT über async_sync_issues()/die Notices-Liste, weil der
    Coordinator während eines abgelehnten Tokens selbst nicht abrufbar
    ist — siehe Docstring der Funktion."""
    source = (INTEGRATION_DIR / "repairs.py").read_text(encoding="utf-8")
    start = source.index("def async_set_demo_mode_paused_issue")
    rest = source[start:]
    end = rest.find("\ndef ", 1)
    body = rest if end == -1 else rest[:end]

    assert 'f"{entry.entry_id}_demo_mode_paused"' in body
    assert "ir.async_create_issue" in body
    assert "ir.async_delete_issue" in body
    assert "severity=ir.IssueSeverity.WARNING" in body
    assert 'translation_key="demo_mode_paused"' in body


def test_clear_issues_removes_the_demo_mode_paused_issue_unconditionally() -> None:
    """Das Issue hängt nicht an active_repair_issues (das führt nur
    async_sync_issues() nach) — ohne einen expliziten Aufruf hier bliebe es
    beim Entladen/Entfernen der Verbindung verwaist stehen."""
    source = (INTEGRATION_DIR / "repairs.py").read_text(encoding="utf-8")
    clear_issues = source[source.index("def async_clear_issues"):]
    assert 'ir.async_delete_issue(hass, DOMAIN, f"{entry.entry_id}_demo_mode_paused")' in clear_issues


def test_init_wires_demo_mode_callbacks_through_hass_add_job() -> None:
    """Wie on_auth_failed: repairs_mod.async_set_demo_mode_paused_issue
    ruft ir.async_create_issue/async_delete_issue auf, die auf dem
    Event-Loop laufen müssen, nicht auf dem Queue-Writer-Hintergrund-Thread."""
    source = (INTEGRATION_DIR / "__init__.py").read_text(encoding="utf-8")
    queue_writer_call = source[source.index("queue_writer = ZeitarchivQueueWriter("):]
    queue_writer_call = queue_writer_call[:queue_writer_call.index("\n    queue_writer.start()")]

    assert "on_demo_mode_detected=lambda: hass.add_job(" in queue_writer_call
    assert "on_demo_mode_resolved=lambda: hass.add_job(" in queue_writer_call
    assert "repairs_mod.async_set_demo_mode_paused_issue, hass, entry, True" in queue_writer_call
    assert "repairs_mod.async_set_demo_mode_paused_issue, hass, entry, False" in queue_writer_call


def test_entity_issue_translations_have_the_demo_mode_paused_key() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        entry = data["issues"]["demo_mode_paused"]
        assert "title" in entry
        assert "{connection}" in entry["description"]
