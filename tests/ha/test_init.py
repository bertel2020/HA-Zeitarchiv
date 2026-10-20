"""Setup, Verbindungsprüfung beim Start und Unload."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivAuthError
from custom_components.zeitarchiv.data import ZeitarchivRuntimeData


async def test_setup_and_unload(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    runtime_data = loaded_entry.runtime_data
    assert isinstance(runtime_data, ZeitarchivRuntimeData)
    assert runtime_data.queue_writer._thread.is_alive()

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    await hass.async_block_till_done()

    assert loaded_entry.state is ConfigEntryState.NOT_LOADED
    assert not runtime_data.queue_writer._thread.is_alive()


async def test_rejected_token_at_setup_starts_reauth(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    mock_client.test_connection.side_effect = ZeitarchivAuthError(
        "abgelehnt", demo_mode=False
    )

    assert not await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()

    assert unload_after_test.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    # Abbruch vor allem anderen: kein Thread, kein Listener bleibt zurück.
    mock_client.write_batch.assert_not_called()


async def test_rejected_token_of_unknown_cause_also_starts_reauth(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    """Ältere App-Versionen liefern kein demo_mode-Feld (None) — derselbe
    Rückfall wie im Queue-Writer: normaler Reauth."""
    mock_client.test_connection.side_effect = ZeitarchivAuthError("abgelehnt")

    assert not await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()

    assert unload_after_test.state is ConfigEntryState.SETUP_ERROR


async def test_rejected_token_in_demo_mode_still_sets_up(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    mock_client.test_connection.side_effect = ZeitarchivAuthError(
        "abgelehnt", demo_mode=True
    )

    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()

    assert unload_after_test.state is ConfigEntryState.LOADED
    assert not hass.config_entries.flow.async_progress()


async def test_unreachable_app_at_setup_still_sets_up(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    """Bewusst kein ConfigEntryNotReady: der Queue-Writer puffert, bis die
    App wieder erreichbar ist."""
    mock_client.test_connection.side_effect = ZeitarchivApiError("weg")
    mock_client.get_notices.side_effect = ZeitarchivApiError("weg")

    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()

    assert unload_after_test.state is ConfigEntryState.LOADED


async def test_remove_entry_deletes_watermark(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    key = f"zeitarchiv_{config_entry.entry_id}_watermark"
    hass_storage[key] = {"version": 1, "key": key, "data": {"sensor.a": 1.0}}
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert key not in hass_storage
