"""Regressionstests für Repair-Issue "text_states_not_archived" und Binärsensor
"Nicht archivierbare Entitäten" (Issue #24).

Wie test_demo_mode_paused_repair.py reine Quelltext-Prüfungen, weil
`homeassistant` in dieser Testumgebung nicht installiert ist."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def test_repairs_creates_and_deletes_the_text_states_issue() -> None:
    source = (INTEGRATION_DIR / "repairs.py").read_text(encoding="utf-8")
    start = source.index("def async_set_text_states_issue")
    body = source[start:source.index("\ndef ", start + 1)]

    assert 'f"{entry.entry_id}_text_states"' in body
    assert "ir.async_create_issue" in body
    assert "ir.async_delete_issue" in body
    assert 'translation_key="text_states_not_archived"' in body


def test_clear_issues_removes_the_text_states_issue() -> None:
    source = (INTEGRATION_DIR / "repairs.py").read_text(encoding="utf-8")
    clear_issues = source[source.index("def async_clear_issues"):]
    assert 'ir.async_delete_issue(hass, DOMAIN, f"{entry.entry_id}_text_states")' in clear_issues


def test_init_publishes_text_states_on_the_event_loop() -> None:
    """state_changed-Listener ohne @callback laufen im Executor. hass.add_job
    bringt den Job nur dann auf den Event-Loop, wenn das Ziel selbst ein
    @callback ist — eine undekorierte Funktion schickt es wieder in den
    Executor, wo Repair-Registry und Dispatcher nicht laufen dürfen."""
    source = (INTEGRATION_DIR / "__init__.py").read_text(encoding="utf-8")
    assert "    @callback\n    def _async_text_states_changed(" in source
    changed = source[source.index("def _async_text_states_changed"):]
    changed = changed[:changed.index("\n    def ", 1)]
    assert "repairs_mod.async_set_text_states_issue(hass, entry, entity_ids)" in changed
    assert "async_dispatcher_send(hass, SIGNAL_TEXT_STATES.format(entry.entry_id))" in changed

    publish = source[source.index("def _publish_text_states"):]
    publish = publish[:publish.index("\n    def ", 1)]
    assert "hass.add_job(_async_text_states_changed," in publish
    assert '"text_states": text_states_view,' in source


def test_binary_sensor_follows_the_text_states_signal() -> None:
    source = (INTEGRATION_DIR / "binary_sensor.py").read_text(encoding="utf-8")
    sensor = source[source.index("class ZeitarchivTextStatesBinarySensor"):]
    assert "_attr_device_class = BinarySensorDeviceClass.PROBLEM" in sensor
    assert "_attr_should_poll = False" in sensor
    assert '_attr_translation_key = "text_states"' in sensor
    assert 'f"{entry.entry_id}_text_states"' in sensor
    assert "SIGNAL_TEXT_STATES.format(self._entry_id)" in sensor
    assert '{"entities": list(entities), "count": len(entities)}' in sensor
    assert 'ZeitarchivTextStatesBinarySensor(entry, device_info, entry_data["text_states"])' in source


def test_text_states_binary_sensor_has_a_name_in_every_language() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        assert data["entity"]["binary_sensor"]["text_states"]["name"]


def test_text_states_issue_translations_have_both_placeholders() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        entry = data["issues"]["text_states_not_archived"]
        assert entry["title"]
        assert "{connection}" in entry["description"]
        assert "{entities}" in entry["description"]
