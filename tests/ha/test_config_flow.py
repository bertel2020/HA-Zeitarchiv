"""Config- und Options-Flow gegen ein echtes Home Assistant."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivAuthError
from custom_components.zeitarchiv.const import (
    CONF_CARD_SHARED_CHARTS,
    CONF_CARD_SHARED_TABLES,
    CONF_API_TOKEN,
    CONF_DECIMAL_PLACES,
    CONF_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITY_PATTERNS,
    DOMAIN,
)

from .conftest import ENTRY_DATA, NOTICES, TOKEN

CONNECTION_ERRORS = [
    (ZeitarchivAuthError("abgelehnt"), "invalid_auth"),
    (ZeitarchivApiError("weg"), "cannot_connect"),
    (RuntimeError("kaputt"), "unknown"),
]


async def _start_user_flow(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


# --- Einrichtung -----------------------------------------------------------


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NAME: "  Testsystem  "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zeitarchiv (Testsystem)"
    assert result["data"] == {**ENTRY_DATA, CONF_NAME: "Testsystem"}
    entry = result["result"]
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(("error", "reason"), CONNECTION_ERRORS)
async def test_user_flow_connection_errors_recover(
    hass: HomeAssistant, mock_client: MagicMock, error: Exception, reason: str
) -> None:
    result = await _start_user_flow(hass)
    mock_client.test_connection.side_effect = error

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}

    mock_client.test_connection.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert await hass.config_entries.async_unload(result["result"].entry_id)


async def test_user_flow_rejects_blank_name(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NAME: "   "}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NAME: "invalid_name"}
    mock_client.test_connection.assert_not_called()


async def test_user_flow_aborts_on_identical_target(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NAME: "Anderer Name"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.test_connection.assert_not_called()


async def test_user_flow_allows_same_endpoint_with_other_token(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Zweites Ziel auf demselben Host/Port bleibt erlaubt (z. B. Demo-Instanz)."""
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**ENTRY_DATA, CONF_NAME: "Demo", CONF_API_TOKEN: "anderer-token"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert await hass.config_entries.async_unload(result["result"].entry_id)


# --- Neu konfigurieren -----------------------------------------------------


async def test_reconfigure_updates_loaded_entry(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    result = await loaded_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    calls_before = mock_client.test_connection.call_count

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**ENTRY_DATA, CONF_NAME: " Neu ", CONF_HOST: "anderer.host"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert loaded_entry.title == "Zeitarchiv (Neu)"
    assert loaded_entry.data[CONF_HOST] == "anderer.host"
    assert loaded_entry.data[CONF_NAME] == "Neu"
    # Flow-Validierung plus genau ein Reload über den Update-Listener.
    assert mock_client.test_connection.call_count == calls_before + 2
    assert loaded_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(("error", "reason"), CONNECTION_ERRORS)
async def test_reconfigure_connection_errors(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    reason: str,
) -> None:
    result = await loaded_entry.start_reconfigure_flow(hass)
    mock_client.test_connection.side_effect = error

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}
    mock_client.test_connection.side_effect = None


async def test_reconfigure_rejects_blank_name(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await loaded_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NAME: ""}
    )

    assert result["errors"] == {CONF_NAME: "invalid_name"}


async def test_reconfigure_rejects_target_of_other_entry(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={**ENTRY_DATA, CONF_NAME: "Test", CONF_API_TOKEN: "anderer-token"},
    ).add_to_hass(hass)
    result = await loaded_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_API_TOKEN: "anderer-token"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}


async def test_reconfigure_keeping_own_target_is_allowed(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Der eigene Entry zählt nicht als Duplikat — sonst ließe sich nur der
    Name nie ändern."""
    result = await loaded_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_NAME: "Umbenannt"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_reloads_entry_whose_setup_failed(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    """Nach ConfigEntryAuthFailed hat HA den Update-Listener schon entfernt —
    der Flow muss selbst neu laden, sonst bliebe der Entry im Fehlerzustand."""
    mock_client.test_connection.side_effect = ZeitarchivAuthError("abgelehnt")
    await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    assert unload_after_test.state is ConfigEntryState.SETUP_ERROR
    assert not unload_after_test.update_listeners

    result = await unload_after_test.start_reconfigure_flow(hass)
    mock_client.test_connection.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_API_TOKEN: "neuer-token"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert unload_after_test.state is ConfigEntryState.LOADED


# --- Reauth ----------------------------------------------------------------


async def test_reauth_updates_token(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    result = await loaded_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "neuer-token"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert loaded_entry.data == {**ENTRY_DATA, CONF_API_TOKEN: "neuer-token"}
    assert loaded_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(("error", "reason"), CONNECTION_ERRORS)
async def test_reauth_connection_errors(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    reason: str,
) -> None:
    result = await loaded_entry.start_reauth_flow(hass)
    mock_client.test_connection.side_effect = error

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "neuer-token"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}
    assert loaded_entry.data[CONF_API_TOKEN] == TOKEN
    mock_client.test_connection.side_effect = None


async def test_reauth_ignores_demo_probe_failure(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Die Demo-Modus-Probe ist best-effort und darf den Reauth nie blockieren."""
    result = await loaded_entry.start_reauth_flow(hass)
    mock_client.get_notices.side_effect = ZeitarchivApiError("weg")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "neuer-token"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reauth_successful"
    mock_client.get_notices.side_effect = None


@pytest.mark.parametrize(
    ("confirm", "reason", "token"),
    [
        (True, "reauth_successful", "demo-token"),
        (False, "demo_mode_reauth_cancelled", TOKEN),
    ],
)
async def test_reauth_to_demo_instance_needs_confirmation(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    mock_client: MagicMock,
    confirm: bool,
    reason: str,
    token: str,
) -> None:
    result = await loaded_entry.start_reauth_flow(hass)
    mock_client.get_notices.return_value = {**NOTICES, "demo_mode": True}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "demo-token"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm_demo_warning"
    assert result["description_placeholders"]["connection"] == loaded_entry.title

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"confirm": confirm}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    assert loaded_entry.data[CONF_API_TOKEN] == token


async def test_reauth_after_failed_setup_loads_entry(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    """Der von ConfigEntryAuthFailed gestartete Reauth bringt den Entry hoch."""
    mock_client.test_connection.side_effect = ZeitarchivAuthError("abgelehnt")
    await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    (flow,) = hass.config_entries.flow.async_progress()

    mock_client.test_connection.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_TOKEN: "neuer-token"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reauth_successful"
    assert unload_after_test.state is ConfigEntryState.LOADED


# --- Options-Flow ----------------------------------------------------------


def _filter_input(**overrides: object) -> dict:
    values = {
        CONF_ENTITIES: ["sensor.temperatur"],
        CONF_ENTITY_PATTERNS: "",
        CONF_EXCLUDE_ENTITY_PATTERNS: "",
        CONF_DECIMAL_PLACES: 2,
        **overrides,
    }
    return {
        "labels": [],
        "additional_selection": {
            CONF_ENTITIES: values[CONF_ENTITIES],
            "areas": [],
            "devices": [],
            CONF_ENTITY_PATTERNS: values[CONF_ENTITY_PATTERNS],
        },
        "exclusions": {
            "exclude_entities": [],
            CONF_EXCLUDE_ENTITY_PATTERNS: values[CONF_EXCLUDE_ENTITY_PATTERNS],
        },
        "value_processing": {CONF_DECIMAL_PLACES: values[CONF_DECIMAL_PLACES]},
    }


async def _open_options_step(
    hass: HomeAssistant, entry: MockConfigEntry, step: str
) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_options_filters_preview_then_save(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    hass.states.async_set("sensor.temperatur", "21.5")
    result = await _open_options_step(hass, loaded_entry, "filters")
    assert result["step_id"] == "filters"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _filter_input(**{CONF_ENTITY_PATTERNS: "Wohnzimmer_*\n"})
    )
    assert result["step_id"] == "filter_preview"
    placeholders = result["description_placeholders"]
    assert placeholders["current_count"] == "1"
    assert "`sensor.temperatur`" in placeholders["current_entities"]
    assert placeholders["decimal_places"] == "2"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_ENTITIES] == ["sensor.temperatur"]
    assert loaded_entry.options[CONF_ENTITY_PATTERNS] == ["wohnzimmer_*"]
    assert loaded_entry.options[CONF_DECIMAL_PLACES] == 2
    assert loaded_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize("field", [CONF_ENTITY_PATTERNS, CONF_EXCLUDE_ENTITY_PATTERNS])
async def test_options_filters_reject_invalid_pattern(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, field: str
) -> None:
    result = await _open_options_step(hass, loaded_entry, "filters")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _filter_input(**{field: "sensor.[abc]"})
    )

    assert result["step_id"] == "filters"
    assert result["errors"] == {"base": "invalid_pattern"}


async def test_options_overview_returns_to_menu(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await _open_options_step(hass, loaded_entry, "overview")
    assert result["step_id"] == "overview"
    assert result["description_placeholders"]["current_count"] == "0"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.MENU


async def test_options_export_then_import_round_trip(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        loaded_entry,
        options={CONF_ENTITIES: ["sensor.temperatur"], CONF_DECIMAL_PLACES: 1},
    )
    await hass.async_block_till_done()

    result = await _open_options_step(hass, loaded_entry, "export")
    assert result["step_id"] == "export"
    exported = result["data_schema"]({})["yaml_config"]
    assert "sensor.temperatur" in exported
    assert "geheimer-token" not in exported
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"yaml_config": exported}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "import"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"yaml_config": exported}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_ENTITIES] == ["sensor.temperatur"]
    # Nachkommastellen gehören nicht zum Export und bleiben beim Import erhalten.
    assert loaded_entry.options[CONF_DECIMAL_PLACES] == 1


async def test_options_import_rejects_invalid_yaml(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await _open_options_step(hass, loaded_entry, "import")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"yaml_config": "format: [unvollständig"}
    )

    assert result["step_id"] == "import"
    assert result["errors"] == {"base": "invalid_yaml"}


async def test_options_preview_truncates_long_entity_lists(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    for index in range(205):
        hass.states.async_set(f"sensor.messwert_{index:03d}", "1")
    result = await _open_options_step(hass, loaded_entry, "filters")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _filter_input(**{CONF_ENTITIES: [], CONF_ENTITY_PATTERNS: "messwert_*"}),
    )

    placeholders = result["description_placeholders"]
    assert placeholders["current_count"] == "205"
    assert placeholders["current_entities"].endswith("- … (+5)")
    assert placeholders["limit_note"] == "⚠ 200 / 205 Entity-IDs"


async def test_options_preview_without_pending_filters_falls_back(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Schutzzweig: über die Oberfläche nicht erreichbar, weil filter_preview
    nur aus filters heraus angesprungen wird. Deshalb direkt am Handler."""
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result = await flow.async_step_filter_preview()

    assert result["step_id"] == "filters"


CARD_ITEMS = {
    "spec_version": 1,
    "items": [{"id": 7, "name": "Verbrauch"}, {"id": 9, "name": "Solar"}],
    "tables": [{"id": 3, "name": "Monat"}],
}


async def test_options_card_sharing_saves_known_ids_only(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, CONF_CARD_SHARED_CHARTS: [7, 99]}
    )
    await hass.async_block_till_done()
    runtime_before = loaded_entry.runtime_data
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_items", return_value=CARD_ITEMS):
        result = await _open_options_step(hass, loaded_entry, "card_sharing")
        assert result["step_id"] == "card_sharing"
        schema = result["data_schema"].schema
        shared = next(key for key in schema if key == CONF_CARD_SHARED_CHARTS)
        # Eine gelöschte ID (99) taucht nicht mehr als Vorgabe auf.
        assert shared.default() == ["7"]
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_CARD_SHARED_CHARTS: ["9", "7"], CONF_CARD_SHARED_TABLES: ["3"]}
        )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_CARD_SHARED_CHARTS] == [7, 9]
    assert loaded_entry.options[CONF_CARD_SHARED_TABLES] == [3]
    # Die Freigabe liest die Karte bei jeder Anfrage; die Verbindung wird dafür nicht neu geladen.
    assert loaded_entry.runtime_data is runtime_before
    assert loaded_entry.state is ConfigEntryState.LOADED


async def test_options_card_sharing_aborts_without_the_app(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    with patch(
        "custom_components.zeitarchiv.api.ZeitarchivClient.get_card_items", side_effect=ZeitarchivApiError("down")
    ):
        result = await _open_options_step(hass, loaded_entry, "card_sharing")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "card_unavailable"


async def test_the_card_sharing_survives_saving_the_filters_and_an_import(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        loaded_entry,
        options={CONF_ENTITIES: ["sensor.temperatur"], CONF_CARD_SHARED_CHARTS: [7], CONF_CARD_SHARED_TABLES: [3]},
    )
    await hass.async_block_till_done()
    hass.states.async_set("sensor.temperatur", "21.5")

    result = await _open_options_step(hass, loaded_entry, "filters")
    result = await hass.config_entries.options.async_configure(result["flow_id"], _filter_input())
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert loaded_entry.options[CONF_CARD_SHARED_CHARTS] == [7]
    assert loaded_entry.options[CONF_CARD_SHARED_TABLES] == [3]

    result = await _open_options_step(hass, loaded_entry, "export")
    exported = result["data_schema"]({})["yaml_config"]
    assert "card_shared" not in exported
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"yaml_config": exported})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "import"})
    await hass.config_entries.options.async_configure(result["flow_id"], {"yaml_config": exported})
    await hass.async_block_till_done()
    assert loaded_entry.options[CONF_CARD_SHARED_CHARTS] == [7]
    assert loaded_entry.options[CONF_CARD_SHARED_TABLES] == [3]


async def test_changing_the_filters_still_reloads_the_connection(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    runtime_before = loaded_entry.runtime_data
    hass.config_entries.async_update_entry(loaded_entry, options={**loaded_entry.options, CONF_ENTITIES: ["sensor.x"]})
    await hass.async_block_till_done()
    assert loaded_entry.runtime_data is not runtime_before
    assert loaded_entry.state is ConfigEntryState.LOADED
