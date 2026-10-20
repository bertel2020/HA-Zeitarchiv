"""Schreibpfad: state_changed → Filter → Queue-Writer → App, samt Wasserstand,
Text-Zuständen und Migration der alten Domainfilter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.const import CONF_ENTITIES, DOMAIN

from .conftest import ENTRY_DATA, wait_for_events

SELECTED = "sensor.temperatur"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(
        entry, options={CONF_ENTITIES: [SELECTED], **options}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_snapshot_and_changes_of_selected_entities_are_sent(
    hass: HomeAssistant,
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    hass.states.async_set(SELECTED, "21.5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.nicht_gewaehlt", "3")

    await _setup(hass, unload_after_test)
    await wait_for_events(hass, written, 1)
    assert [(e["entity_id"], e["value"]) for e in written] == [(SELECTED, 21.5)]

    # Reine Attributänderung: kein neuer Archivpunkt.
    hass.states.async_set(SELECTED, "21.5", {"unit_of_measurement": "°C", "x": 1})
    hass.states.async_set(SELECTED, "22.25", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.nicht_gewaehlt", "4")
    await wait_for_events(hass, written, 2)

    assert [(e["entity_id"], e["value"]) for e in written] == [
        (SELECTED, 21.5),
        (SELECTED, 22.25),
    ]


async def test_watermark_skips_already_sent_values_after_reload(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    hass.states.async_set(SELECTED, "21.5")
    await _setup(hass, unload_after_test)
    await wait_for_events(hass, written, 1)
    key = f"{DOMAIN}_{unload_after_test.entry_id}_watermark"
    assert SELECTED in hass_storage[key]["data"]

    assert await hass.config_entries.async_reload(unload_after_test.entry_id)
    await hass.async_block_till_done()

    # Unveränderter Zustand seit dem letzten bestätigten Batch: kein Duplikat.
    assert len(written) == 1


async def test_text_states_raise_repair_and_binary_sensor(
    hass: HomeAssistant,
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    hass.states.async_set(SELECTED, "Idle")
    await _setup(hass, unload_after_test)

    issue_id = f"{unload_after_test.entry_id}_text_states"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_placeholders["entities"] == SELECTED
    sensor_id = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{unload_after_test.entry_id}_text_states"
    )
    state = hass.states.get(sensor_id)
    assert state.state == "on"
    assert state.attributes["entities"] == [SELECTED]
    assert written == []

    hass.states.async_set(SELECTED, "20")
    await wait_for_events(hass, written, 1)

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert hass.states.get(sensor_id).state == "off"


async def test_migration_replaces_legacy_domains_with_entities(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    hass.states.async_set("sensor.alt", "1")
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, data=dict(ENTRY_DATA), options={"domains": ["sensor"]}
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert "domains" not in entry.options
    assert "sensor.alt" in entry.options[CONF_ENTITIES]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_migration_from_future_version_fails(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=3, data=dict(ENTRY_DATA))
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_unload_fails_when_queue_writer_does_not_stop(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    writer = loaded_entry.runtime_data.queue_writer
    real_stop = writer.stop
    with patch.object(writer, "stop", return_value=False):
        assert not await hass.config_entries.async_unload(loaded_entry.entry_id)
    # Den Thread trotzdem beenden, sonst bliebe er über den Test hinaus stehen.
    await hass.async_add_executor_job(real_stop)
