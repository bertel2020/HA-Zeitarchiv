"""Regressionstests für die Demo-Modus-Warnung in async_step_reauth_confirm
(DEMO_MODUS_REAUTH_PLAN.md, zweite Sicherheitsebene neben
queue_writer.py::_probe_demo_mode()).

config_flow.py importiert `homeassistant` (siehe test_config_flow_sortable_
entities.py) — deshalb reine Quelltext-Prüfungen statt eines echten Imports/
einer Instanziierung, nach demselben etablierten Muster."""

from __future__ import annotations

import json
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"
CONFIG_FLOW = (INTEGRATION_DIR / "config_flow.py").read_text(encoding="utf-8")


def test_reauth_target_is_demo_mode_defaults_to_false_on_any_failure() -> None:
    """Der Zusatz-Check darf den eigentlichen Reauth nie selbst blockieren
    — jeder Fehlschlag (Netz, ältere App-Version) gilt als "kein Demo-Modus"."""
    start = CONFIG_FLOW.index("async def _reauth_target_is_demo_mode")
    body = CONFIG_FLOW[start:CONFIG_FLOW.index("\nclass ZeitarchivConfigFlow")]
    assert "except ZeitarchivApiError:" in body
    assert 'return notices.get("demo_mode") is True' in body


def test_reauth_confirm_routes_to_the_demo_warning_step_when_detected() -> None:
    start = CONFIG_FLOW.index("async def async_step_reauth_confirm(")
    end = CONFIG_FLOW.index("async def async_step_reauth_confirm_demo_warning")
    body = CONFIG_FLOW[start:end]
    assert "if await _reauth_target_is_demo_mode(self.hass, data):" in body
    assert "return await self.async_step_reauth_confirm_demo_warning()" in body


def test_demo_warning_step_uses_the_reauth_entry_title_and_can_be_cancelled() -> None:
    start = CONFIG_FLOW.index("async def async_step_reauth_confirm_demo_warning")
    end = CONFIG_FLOW.index("\n    @staticmethod", start)
    body = CONFIG_FLOW[start:end]
    assert 'description_placeholders={"connection": self._get_reauth_entry().title}' in body
    assert 'self.async_abort(reason="demo_mode_reauth_cancelled")' in body
    assert "self.async_update_and_abort(self._get_reauth_entry(), data=data)" in body


def test_user_and_reconfigure_steps_do_not_check_demo_mode() -> None:
    """Bewusst nur bei reauth_confirm — user/reconfigure sind bewusste
    Aktionen, dort ist eine Demo-Instanz als Ziel plausibel gewollt."""
    for step in ("async def async_step_user(", "async def async_step_reconfigure("):
        start = CONFIG_FLOW.index(step)
        end = CONFIG_FLOW.index("\n    async def async_step_", start + 1)
        body = CONFIG_FLOW[start:end]
        assert "_reauth_target_is_demo_mode" not in body


def test_translations_have_the_demo_warning_step_and_abort_reason() -> None:
    for name in ("strings.json", "translations/de.json", "translations/en.json"):
        data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
        step = data["config"]["step"]["reauth_confirm_demo_warning"]
        assert "{connection}" in step["description"]
        assert "confirm" in step["data"]
        assert "demo_mode_reauth_cancelled" in data["config"]["abort"]
