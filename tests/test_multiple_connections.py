"""Regressionstests für mehrere parallele Zeitarchiv-Config-Entries."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLOW_PATH = ROOT / "custom_components" / "zeitarchiv" / "config_flow.py"


def test_config_flow_does_not_deduplicate_by_endpoint() -> None:
    source = FLOW_PATH.read_text(encoding="utf-8")

    assert "self._abort_if_unique_id_configured()" not in source
    assert "self.async_set_unique_id(" not in source
    assert "CONF_NAME" in source
    assert 'title=f"Zeitarchiv ({name})", data=user_input' in source


def test_form_schema_contains_no_custom_callable_validator() -> None:
    source = FLOW_PATH.read_text(encoding="utf-8")

    assert 'vol.Required(CONF_NAME, default="Produktivsystem"): str' in source
    assert "): _connection_name" not in source
    assert 'errors[CONF_NAME] = "invalid_name"' in source


def test_reconfigure_updates_connection_name_and_title() -> None:
    source = FLOW_PATH.read_text(encoding="utf-8")

    assert "user_input = {**user_input, CONF_NAME: name}" in source
    assert "data=user_input" in source
    assert 'title=f"Zeitarchiv ({name})"' in source
    assert 'default=entry.data.get(CONF_NAME, "Produktivsystem")' in source


def test_reconfigure_and_reauth_rely_on_update_listener_for_reload() -> None:
    source = FLOW_PATH.read_text(encoding="utf-8")

    assert source.count("self.async_update_and_abort(") == 2
    assert "return self.async_update_reload_and_abort(" not in source
    assert "await self.hass.config_entries.async_reload(" not in source


def test_connection_name_is_translated_in_all_catalogs() -> None:
    component = ROOT / "custom_components" / "zeitarchiv"
    for relative_path in ("strings.json", "translations/de.json", "translations/en.json"):
        catalog = json.loads((component / relative_path).read_text(encoding="utf-8"))
        steps = catalog["config"]["step"]
        assert "name" in steps["user"]["data"]
        assert "name" in steps["reconfigure"]["data"]
