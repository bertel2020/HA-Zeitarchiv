"""Der Auswahl-Assistent schreibt Optionen und darf die Freigabe der Karte dabei nicht zurückdrehen."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.const import CONF_CARD_SHARED_CHARTS, CONF_CARD_SHARED_TABLES, CONF_ENTITIES
from custom_components.zeitarchiv.selection_sync import SelectionManager


async def test_a_sharing_changed_while_the_jobs_run_is_not_turned_back(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, CONF_CARD_SHARED_CHARTS: [7], CONF_CARD_SHARED_TABLES: [3]}
    )
    await hass.async_block_till_done()
    client = MagicMock()
    client.get_selection_jobs.return_value = [{"id": "job"}]
    manager = SelectionManager(hass, loaded_entry, client, lambda _state: True)
    await manager.async_setup()
    # Die Optionen, die der Assistent am Anfang kopiert (mit der damaligen Freigabe).
    outcome = SimpleNamespace(
        acks=[{"job": 1}], label_targets=[], include_targets=[], added_patterns=[],
        options={**loaded_entry.options, CONF_ENTITIES: ["sensor.neu"]}, options_changed=True,
    )
    calls = {"flush": 0}

    async def flush() -> None:
        calls["flush"] += 1
        if calls["flush"] == 2:
            # Ein Administrator entzieht die Freigabe, während der Assistent noch auf das Netz wartet.
            hass.config_entries.async_update_entry(
                loaded_entry, options={**loaded_entry.options, CONF_CARD_SHARED_CHARTS: [], CONF_CARD_SHARED_TABLES: [3, 4]}
            )

    with (
        patch("custom_components.zeitarchiv.selection_sync.apply_jobs", return_value=outcome),
        patch.object(manager, "_async_flush_acks", side_effect=flush),
    ):
        await manager._async_run("rev")
    await hass.async_block_till_done()
    assert loaded_entry.options[CONF_ENTITIES] == ["sensor.neu"]
    assert loaded_entry.options[CONF_CARD_SHARED_CHARTS] == []
    assert loaded_entry.options[CONF_CARD_SHARED_TABLES] == [3, 4]
