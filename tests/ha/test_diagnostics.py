"""Diagnose-Download."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.api import ZeitarchivApiError
from custom_components.zeitarchiv.diagnostics import async_get_config_entry_diagnostics

from .conftest import TOKEN, wait_for_events


async def test_diagnostics_redacts_token_and_reports_live_state(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_client: MagicMock,
    written: list[dict],
) -> None:
    hass.config_entries.async_update_entry(
        loaded_entry, options={"entities": ["sensor.temperatur"]}
    )
    await hass.async_block_till_done()
    hass.states.async_set("sensor.temperatur", "20")
    await wait_for_events(hass, written, 1)

    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert TOKEN not in str(diagnostics)
    assert diagnostics["config_entry"]["data"]["api_token"] == "**REDACTED**"
    assert diagnostics["connection"] == {
        "reachable_now": True,
        "error": None,
        "host": "zeitarchiv.local",
        "port": 8127,
    }
    assert diagnostics["queue"]["sent_count_since_start"] == 1
    assert diagnostics["queue"]["last_success_seconds_ago"] is not None
    assert diagnostics["filters"]["matching_entities_now"] == 1
    assert diagnostics["filters"]["included_entities_count"] == 1


async def test_diagnostics_reports_unreachable_app(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.test_connection.side_effect = ZeitarchivApiError("App nicht erreichbar")

    diagnostics = await async_get_config_entry_diagnostics(hass, loaded_entry)

    assert diagnostics["connection"]["reachable_now"] is False
    assert diagnostics["connection"]["error"] == "App nicht erreichbar"
    assert diagnostics["queue"]["last_success_seconds_ago"] is None
    mock_client.test_connection.side_effect = None
