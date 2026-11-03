"""Lebenszyklus des Schreibpfads: Herunterfahren, Neuladen, Wasserstand, Entladen (Code-Review Phase 4).

Ziel der Integration: Fällt die App aus, geht nichts verloren. Das galt bisher nur, solange Home Assistant lief.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.api import ZeitarchivAuthError
from custom_components.zeitarchiv.const import (
    CONF_CARD_SHARED_CHARTS,
    CONF_CARD_SHARED_TABLES,
    CONF_ENTITIES,
    DOMAIN,
)
from custom_components.zeitarchiv.queue_writer import ZeitarchivQueueWriter

from .conftest import wait_for_events
from .test_config_flow import _open_options_step

SELECTED = "sensor.temperatur"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(entry, options={CONF_ENTITIES: [SELECTED]})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _wait_for_attempt(mock_client: MagicMock) -> None:
    async with asyncio.timeout(3):
        while not mock_client.write_batch.called:
            await asyncio.sleep(0.01)


def _pending_key(entry: MockConfigEntry) -> str:
    return f"{DOMAIN}_{entry.entry_id}_pending"


def _watermark_key(entry: MockConfigEntry) -> str:
    return f"{DOMAIN}_{entry.entry_id}_watermark"


# ---------------------------------------------------------------- Herunterfahren und Neuladen


async def test_shutting_down_home_assistant_saves_what_was_not_sent(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    unload_after_test: MockConfigEntry,
) -> None:
    """Beim Herunterfahren entlädt Home Assistant die Einträge nicht; der Worker ist ein Daemon-Thread."""
    mock_client.write_batch.side_effect = RuntimeError("App nicht erreichbar")
    hass.states.async_set(SELECTED, "21.5", {"unit_of_measurement": "°C"})
    await _setup(hass, unload_after_test)
    await _wait_for_attempt(mock_client)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    saved = hass_storage[_pending_key(unload_after_test)]["data"]
    assert [event["entity_id"] for event in saved] == [SELECTED]
    assert saved[0]["value"] == 21.5


async def test_a_reload_resends_what_the_app_never_confirmed(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    unload_after_test: MockConfigEntry,
) -> None:
    """Früher verwarf stop() nach der Drain-Phase den Rückstau: ein Neuladen (auch durch den Auswahl-Assistenten)
    hätte nach einem Ausfall der App den ganzen Puffer verloren."""
    mock_client.write_batch.side_effect = RuntimeError("App nicht erreichbar")
    hass.states.async_set(SELECTED, "21.5")
    await _setup(hass, unload_after_test)
    await _wait_for_attempt(mock_client)
    first_event_id = mock_client.write_batch.call_args_list[0].args[0][0]["event_id"]

    assert await hass.config_entries.async_reload(unload_after_test.entry_id)
    await hass.async_block_till_done()
    # Der Rückstau wurde gelesen und die Datei gelöscht (sonst ginge er bei jedem Start erneut hinaus).
    assert _pending_key(unload_after_test) not in hass_storage

    sent: list[dict] = []
    mock_client.write_batch.side_effect = sent.extend
    async with asyncio.timeout(3):
        while first_event_id not in {event["event_id"] for event in sent}:
            await asyncio.sleep(0.01)


async def test_a_clean_unload_leaves_no_pending_file(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    hass.states.async_set(SELECTED, "21.5")
    await _setup(hass, unload_after_test)
    await wait_for_events(hass, written, 1)

    assert await hass.config_entries.async_unload(unload_after_test.entry_id)
    await hass.async_block_till_done()

    assert _pending_key(unload_after_test) not in hass_storage


async def test_removing_the_entry_deletes_the_pending_file(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    hass_storage[_pending_key(config_entry)] = {
        "version": 1, "minor_version": 1, "key": _pending_key(config_entry), "data": [{"entity_id": "sensor.x"}],
    }
    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert _pending_key(config_entry) not in hass_storage


# ---------------------------------------------------------------- Wasserstand


async def test_the_watermark_is_saved_with_a_delay_and_flushed_on_unload(
    hass: HomeAssistant,
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    """Nach jedem Batch die ganze Datei zu schreiben (alle paar Sekunden) belastet SD-Karten; ein Neuladen liest
    aber die Datei, nicht den ausstehenden Zwischenspeicher — deshalb beim Entladen sofort schreiben."""
    with (
        patch.object(Store, "async_delay_save", autospec=True) as delay_save,
        patch.object(Store, "async_save", autospec=True) as save,
    ):
        hass.states.async_set(SELECTED, "21.5")
        await _setup(hass, unload_after_test)
        await wait_for_events(hass, written, 1)

        delayed = [call for call in delay_save.call_args_list if call.args[0].key == _watermark_key(unload_after_test)]
        assert delayed and all(call.args[2] >= 10 for call in delayed)
        assert not [call for call in save.call_args_list if call.args[0].key == _watermark_key(unload_after_test)]

        assert await hass.config_entries.async_unload(unload_after_test.entry_id)
        await hass.async_block_till_done()

    saved = [call for call in save.call_args_list if call.args[0].key == _watermark_key(unload_after_test)]
    assert len(saved) == 1
    assert SELECTED in saved[0].args[1]


async def test_watermark_entries_of_entities_that_no_longer_exist_are_dropped(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    """Ohne das wüchse die Datei mit jeder je gesendeten Entität. Eine Entität nur in der Registry (ihre
    Integration ist noch nicht geladen) behält ihren Eintrag."""
    registry = er.async_get(hass)
    registered = registry.async_get_or_create("sensor", "test", "uid-1", suggested_object_id="nur_registry")
    key = _watermark_key(unload_after_test)
    hass_storage[key] = {
        "version": 1, "minor_version": 1, "key": key,
        "data": {"sensor.geloescht": 1.0, registered.entity_id: 2.0, SELECTED: 3.0},
    }
    hass.states.async_set(SELECTED, "21.5")
    await _setup(hass, unload_after_test)
    await wait_for_events(hass, written, 1)

    # Geschrieben wird verzögert, beim Entladen sofort.
    assert await hass.config_entries.async_unload(unload_after_test.entry_id)
    await hass.async_block_till_done()
    assert set(hass_storage[key]["data"]) == {registered.entity_id, SELECTED}


# ---------------------------------------------------------------- Event-Loop und Reihenfolge


async def test_state_changes_are_handled_in_the_event_loop(
    hass: HomeAssistant,
    mock_client: MagicMock,
    written: list[dict],
    unload_after_test: MockConfigEntry,
) -> None:
    """Ohne @callback schickte Home Assistant jedes state_changed des ganzen Systems in den Executor."""
    await _setup(hass, unload_after_test)
    loop_thread = threading.get_ident()
    seen: list[int] = []

    def spy(old: str | None, new: str) -> bool:
        seen.append(threading.get_ident())
        return True

    with patch("custom_components.zeitarchiv.is_state_value_change", spy):
        hass.states.async_set(SELECTED, "20.5")
        hass.states.async_set("sensor.nicht_gewaehlt", "1")
        await hass.async_block_till_done()

    assert seen and set(seen) == {loop_thread}


async def test_unloading_stops_the_writer_before_the_repair_issues_are_cleared(
    hass: HomeAssistant,
    mock_client: MagicMock,
    unload_after_test: MockConfigEntry,
) -> None:
    """In den Sekunden des Beendens kann der Worker noch eine Repair-Karte oder einen Reauth auslösen."""
    await _setup(hass, unload_after_test)
    order: list[str] = []
    original_stop = ZeitarchivQueueWriter.stop

    def stop(self: ZeitarchivQueueWriter, *args: Any, **kwargs: Any) -> bool:
        order.append("stop")
        return original_stop(self, *args, **kwargs)

    with (
        patch.object(ZeitarchivQueueWriter, "stop", stop),
        patch("custom_components.zeitarchiv.repairs_mod.async_clear_issues", lambda *_a: order.append("clear")),
    ):
        assert await hass.config_entries.async_unload(unload_after_test.entry_id)
        await hass.async_block_till_done()

    assert order == ["stop", "clear"]


# ---------------------------------------------------------------- Token und Options-Flow


async def test_a_rejected_token_in_the_notices_poll_starts_the_reauth(
    hass: HomeAssistant, mock_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    """Sonst käme der Hinweis nur vom Queue-Writer, und der meldet sich erst, wenn ein Batch scheitert."""
    mock_client.get_notices.side_effect = ZeitarchivAuthError("abgelehnt")
    await loaded_entry.runtime_data.notices_coordinator.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    mock_client.get_notices.side_effect = None


async def test_the_card_sharing_step_survives_an_unexpected_answer_of_the_app(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Fehlende Schlüssel in der Antwort der App enden nicht mit "Unknown error" (KeyError), sondern lassen den
    Eintrag weg."""
    listed = {
        "items": [{"id": 7, "name": "Verbrauch"}, {"name": "ohne ID"}, {"id": 8}, "kein Objekt", {"id": "x", "name": "?"}],
        "tables": [{"id": 3, "name": "Monat"}],
    }
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_items", return_value=listed):
        result = await _open_options_step(hass, loaded_entry, "card_sharing")
        assert result["step_id"] == "card_sharing"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_CARD_SHARED_CHARTS: ["7"], CONF_CARD_SHARED_TABLES: ["3"]}
        )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_CARD_SHARED_CHARTS] == [7]
    assert loaded_entry.options[CONF_CARD_SHARED_TABLES] == [3]


def test_unusable_form_values_and_items_are_skipped_not_fatal() -> None:
    """Die Schemaprüfung der Oberfläche lässt solche Werte nicht durch; der Handler hält sie trotzdem aus."""
    from custom_components.zeitarchiv.config_flow import _known_ids, _named_items

    assert _named_items([{"id": 1, "name": "a"}, {"id": "2", "name": "b"}, {"id": None, "name": "c"}, {"id": 3}, 5]) == {
        1: "a", 2: "b",
    }
    assert _named_items(None) == {} and _named_items({"id": 1}) == {}
    known = {1: "a", 2: "b"}
    assert _known_ids(["2", "abc", None, "1", "1", "99"], known) == [1, 2]
    assert _known_ids("12", known) == [] and _known_ids(None, known) == []
