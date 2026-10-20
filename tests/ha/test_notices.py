"""Rückkanal App → HA: Meldungen-Coordinator, Repairs und die Sensoren daraus."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_component import async_update_entity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv import repairs
from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivAuthError
from custom_components.zeitarchiv.const import DOMAIN

from .conftest import NOTICES, wait_for_events

BACKUP = {
    "filename": "zeitarchiv-2026-10-20.tar",
    "size_bytes": 1234,
    "finished_at": 1_760_000_000,
    "external": {"status": "ok", "target": "webdav", "finished_at": 1_760_000_100},
}


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.notices_coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_notices_drive_health_sensors_and_repairs(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.get_notices.return_value = {
        **NOTICES,
        "notices": [
            {"id": "backup.job_failed", "severity": "error", "detail": "Platte voll"},
            {"id": "system.index_optimization", "severity": "info"},
            # warn-Stufe: nur Health-Sensor, erst die error-Stufe wird ein Repair.
            {"id": "housekeeping.host_disk_space_low", "severity": "warn"},
        ],
    }
    await _refresh(hass, loaded_entry)

    backup = hass.states.get(_entity_id(hass, loaded_entry, "binary_sensor", "backup_failed"))
    assert backup.state == "on"
    assert backup.attributes["reasons"] == ["backup.job_failed"]
    assert backup.attributes["details"] == ["Platte voll"]
    health = hass.states.get(_entity_id(hass, loaded_entry, "binary_sensor", "health_issue"))
    assert health.state == "on"

    registry = ir.async_get(hass)
    backup_issue = registry.async_get_issue(DOMAIN, f"{loaded_entry.entry_id}_backup.job_failed")
    assert backup_issue.severity is ir.IssueSeverity.ERROR
    assert backup_issue.translation_placeholders["detail"] == "Platte voll"
    assert (
        registry.async_get_issue(
            DOMAIN, f"{loaded_entry.entry_id}_housekeeping.host_disk_space_low"
        )
        is None
    )

    mock_client.get_notices.return_value = NOTICES
    await _refresh(hass, loaded_entry)

    assert registry.async_get_issue(DOMAIN, f"{loaded_entry.entry_id}_backup.job_failed") is None
    assert hass.states.get(backup.entity_id).state == "off"


async def test_repairs_are_removed_on_unload(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.get_notices.return_value = {
        **NOTICES,
        "notices": [{"id": "integration.outdated", "severity": "warn"}],
    }
    await _refresh(hass, loaded_entry)
    issue_id = f"{loaded_entry.entry_id}_integration.outdated"
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, issue_id).severity is ir.IssueSeverity.WARNING

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)

    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_latest_backup_and_mode_sensors(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.get_notices.return_value = {**NOTICES, "latest_backup": BACKUP}
    await _refresh(hass, loaded_entry)

    backup = hass.states.get(_entity_id(hass, loaded_entry, "sensor", "latest_backup"))
    assert backup.state == "2025-10-09T08:53:20+00:00"
    assert backup.attributes["filename"] == BACKUP["filename"]
    assert backup.attributes["external_target"] == "webdav"
    assert backup.attributes["external_finished_at"] == "2025-10-09T08:55:00+00:00"
    mode = hass.states.get(_entity_id(hass, loaded_entry, "sensor", "mode"))
    assert mode.state == "produktiv"
    assert mode.attributes["icon"] == "mdi:check-decagram-outline"


async def test_demo_mode_target_is_shown_as_demo_not_unavailable(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Im Demo-Modus lehnt /api/notices den Token ab; /api/health verrät
    aber den Demo-Modus. Health-Sensoren zeigen dann "Unbekannt" statt "Aus"."""
    mock_client.get_notices.side_effect = ZeitarchivAuthError("abgelehnt")
    mock_client.test_connection.side_effect = ZeitarchivAuthError(
        "abgelehnt", demo_mode=True
    )
    await _refresh(hass, loaded_entry)

    mode = hass.states.get(_entity_id(hass, loaded_entry, "sensor", "mode"))
    assert mode.state == "demo"
    assert mode.attributes["icon"] == "mdi:flask-outline"
    backup = hass.states.get(_entity_id(hass, loaded_entry, "binary_sensor", "backup_failed"))
    assert backup.state == STATE_UNKNOWN
    latest = hass.states.get(_entity_id(hass, loaded_entry, "sensor", "latest_backup"))
    assert latest.state == STATE_UNKNOWN
    mock_client.test_connection.side_effect = None


async def test_rejected_token_without_demo_signal_makes_sensors_unavailable(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.get_notices.side_effect = ZeitarchivAuthError("abgelehnt")
    # Probe gelingt unerwartet: kein Demo-Signal ableitbar.
    await _refresh(hass, loaded_entry)
    mode_id = _entity_id(hass, loaded_entry, "sensor", "mode")
    assert hass.states.get(mode_id).state == STATE_UNAVAILABLE

    # Probe scheitert selbst: ebenfalls kein Demo-Signal.
    mock_client.test_connection.side_effect = ZeitarchivApiError("weg")
    await _refresh(hass, loaded_entry)
    assert hass.states.get(mode_id).state == STATE_UNAVAILABLE

    mock_client.get_notices.side_effect = ZeitarchivApiError("weg")
    await _refresh(hass, loaded_entry)
    assert hass.states.get(mode_id).state == STATE_UNAVAILABLE
    mock_client.test_connection.side_effect = None


async def test_demo_mode_paused_issue(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    issue_id = f"{loaded_entry.entry_id}_demo_mode_paused"
    registry = ir.async_get(hass)

    repairs.async_set_demo_mode_paused_issue(hass, loaded_entry, True)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    repairs.async_set_demo_mode_paused_issue(hass, loaded_entry, False)
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_text_states_issue_lists_at_most_ten_entities(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    entity_ids = tuple(f"sensor.text_{index:02d}" for index in range(12))

    repairs.async_set_text_states_issue(hass, loaded_entry, entity_ids)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"{loaded_entry.entry_id}_text_states"
    )
    assert issue.translation_placeholders["entities"].endswith("sensor.text_09 (+2)")


async def test_diagnostic_sensors_follow_the_queue_writer(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_client: MagicMock,
    written: list[dict],
) -> None:
    sensors = {
        key: _entity_id(hass, loaded_entry, "sensor", key)
        for key in ("last_success", "sent_count", "queue_size", "dropped_count")
    }
    hass.config_entries.async_update_entry(
        loaded_entry, options={"entities": ["sensor.temperatur"]}
    )
    await hass.async_block_till_done()
    hass.states.async_set("sensor.temperatur", "20")
    await wait_for_events(hass, written, 1)

    for entity_id in sensors.values():
        await async_update_entity(hass, entity_id)

    assert hass.states.get(sensors["sent_count"]).state == "1"
    assert hass.states.get(sensors["queue_size"]).state == "0"
    assert hass.states.get(sensors["dropped_count"]).state == "0"
    assert hass.states.get(sensors["last_success"]).state not in (
        STATE_UNKNOWN,
        STATE_UNAVAILABLE,
    )
