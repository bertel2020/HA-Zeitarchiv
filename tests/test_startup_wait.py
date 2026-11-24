"""Regressionstest: Zeitarchiv sendet erst, wenn Home Assistant vollständig gestartet ist.

Beim Neustart liefern Entitäten kurz Rohwerte (z. B. Wh vor einer umgestellten
Einheit) oder "unavailable" (Standalone-Issue HA-Apps#11). Reine Quelltext-
Prüfung, weil `homeassistant` in dieser Testumgebung nicht installiert ist."""

from __future__ import annotations

from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"
SOURCE = (INTEGRATION_DIR / "__init__.py").read_text(encoding="utf-8")


def test_snapshot_waits_for_home_assistant_start() -> None:
    assert "from homeassistant.helpers.start import async_at_started" in SOURCE
    assert "entry.async_on_unload(async_at_started(hass, _initial_snapshot))" in SOURCE
    snapshot = SOURCE[SOURCE.index("def _initial_snapshot"):]
    snapshot = snapshot[:snapshot.index("\n    # Erst nach vollständigem HA-Start")]
    assert "hass_started = True" in snapshot
    assert snapshot.index("hass_started = True") < snapshot.index("_enqueue_state(state)")
    assert "hass.states.async_all()" in snapshot


def test_nothing_is_enqueued_before_start() -> None:
    enqueue = SOURCE[SOURCE.index("    def _enqueue_state"):]
    enqueue = enqueue[:enqueue.index("filters.matches")]
    assert "if not hass_started:\n            return False" in enqueue
    handler = SOURCE[SOURCE.index("def _handle_state_changed"):]
    handler = handler[:handler.index("new_state: State | None")]
    assert "if not hass_started:\n            return" in handler


def test_snapshot_is_only_taken_inside_the_started_callback() -> None:
    setup = SOURCE[:SOURCE.index("def _initial_snapshot")]
    assert "_enqueue_state(state) for state in" not in setup
