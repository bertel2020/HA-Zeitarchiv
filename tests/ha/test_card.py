"""Lovelace-Karte: WebSocket-Befehle (Administratoren, Freigabe für andere) und Auslieferung der Dateien."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator, WebSocketGenerator

from custom_components.zeitarchiv import card
from custom_components.zeitarchiv.card import FAILURE_SECONDS, MAX_APP_QUERIES, MAX_QUEUED_OTHERS
from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivCardError
from custom_components.zeitarchiv.const import DOMAIN

from .conftest import NOTICES

ITEMS = {"spec_version": 1, "items": [{"id": 7, "name": "Verbrauch", "kind": "chart", "chart_type": "auto", "supported": True}]}
CHART = {"spec_version": 1, "id": 7, "name": "Verbrauch", "supported": True, "spec": {"entityIds": "[]"}, "data": {"series": []}}


@pytest.fixture(autouse=True)
async def web_stub(hass: HomeAssistant) -> None:
    """Webserver und WebSocket stehen vor der Integration, wie in einem echten Home
    Assistant (after_dependencies). Das echte Frontend braucht das Paket
    hass_frontend, das in dieser Testumgebung fehlt; die Karte meldet sich nur an
    dessen Liste der Module-URLs an."""
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "websocket_api", {})
    hass.data[DATA_EXTRA_MODULE_URL] = set()


@pytest.fixture
def card_client(mock_client: MagicMock) -> Generator[MagicMock]:
    """Die App meldet die Fähigkeit "cards" und beantwortet die beiden Abrufe."""
    mock_client.get_notices.return_value = {**NOTICES, "capabilities": ["cards"]}
    mock_client.get_card_items.return_value = ITEMS
    mock_client.get_card_chart.return_value = CHART
    with (
        patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_items", mock_client.get_card_items),
        patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_chart", mock_client.get_card_chart),
    ):
        yield mock_client


async def _call(client, message: dict[str, Any]) -> dict[str, Any]:
    """Eine Nachricht je Aufruf; Home Assistant verlangt je Verbindung steigende Nummern."""
    client.last_id = getattr(client, "last_id", 0) + 1
    await client.send_json({"id": client.last_id, **message})
    return await client.receive_json()


async def test_an_administrator_gets_the_items(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/items"})
    assert response["success"] is True
    # Der Administrator sieht je Eintrag, ob ihn auch andere Benutzer sehen (Hinweis im Editor).
    assert response["result"] == {
        "spec_version": 1,
        "items": [{**ITEMS["items"][0], "shared": False}],
        "tables": [],
    }


async def test_a_chart_is_asked_for_by_whole_number_and_day_only(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7, "at": "2026-10-01"})
    assert response["success"] is True
    assert response["result"] == CHART
    card_client.get_card_chart.assert_called_once_with(7, "2026-10-01", 0)


@pytest.mark.parametrize(
    "arguments",
    [
        {"chart_id": 0},
        {"chart_id": -3},
        {"chart_id": "7"},
        {"chart_id": 7.5},
        {"chart_id": "7&x=1"},
        {"chart_id": 7, "at": "gestern"},
        {"chart_id": 7, "at": "2026-10-01/../x"},
        {},
    ],
)
async def test_anything_but_a_whole_number_and_a_day_is_refused(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry,
    arguments: dict[str, Any],
) -> None:
    """Die Integration gibt nie frei gewählten Text an die App weiter."""
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/chart", **arguments})
    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"
    card_client.get_card_chart.assert_not_called()


async def test_other_users_may_not_ask_for_what_is_not_shared(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    card_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)
    response = await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7})
    assert response["success"] is False
    assert response["error"]["code"] == "unauthorized"
    card_client.get_card_chart.assert_not_called()
    # Die Auswahl ist für sie leer, ohne dass etwas durchsickert.
    response = await _call(client, {"type": "zeitarchiv/card/items"})
    assert response["success"] is True
    assert response["result"]["items"] == [] and response["result"]["tables"] == []


async def test_other_users_see_what_an_administrator_shared(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    card_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    card_client.get_card_items.return_value = {
        "spec_version": 1,
        "items": [{"id": 7, "name": "Verbrauch"}, {"id": 8, "name": "Geheim"}],
        "tables": [{"id": 3, "name": "Monat"}, {"id": 4, "name": "Privat"}],
    }
    hass.config_entries.async_update_entry(
        loaded_entry, options={**loaded_entry.options, "card_shared_charts": [7], "card_shared_tables": [3]}
    )
    await hass.async_block_till_done()
    client = await hass_ws_client(hass, hass_read_only_access_token)
    items = (await _call(client, {"type": "zeitarchiv/card/items"}))["result"]
    assert [item["id"] for item in items["items"]] == [7]
    assert [item["id"] for item in items["tables"]] == [3]
    assert (await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7}))["success"] is True
    # Ein anderes Chart, und ein Chart ist keine Tabelle gleicher Nummer.
    assert (await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 8}))["error"]["code"] == "unauthorized"
    assert (await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 3}))["error"]["code"] == "unauthorized"
    # Für Administratoren bleibt die Auswahl vollständig.
    admin = await hass_ws_client(hass)
    assert len((await _call(admin, {"type": "zeitarchiv/card/items"}))["result"]["items"]) == 2


async def test_a_second_ask_within_the_cache_time_does_not_reach_the_app(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    client = await hass_ws_client(hass)
    for _ in range(3):
        assert (await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7}))["success"] is True
    assert card_client.get_card_chart.call_count == 1
    # Ein anderes Chart oder ein anderer Stichtag ist eine eigene Frage.
    await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 8})
    await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7, "at": "2026-10-01"})
    assert card_client.get_card_chart.call_count == 3


async def test_the_cache_expires(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    client = await hass_ws_client(hass)
    with patch.object(card, "CACHE_SECONDS", 0.0):
        await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7})
        await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7})
    assert card_client.get_card_chart.call_count == 2


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ZeitarchivCardError("weg", 404), "not_found"),
        (ZeitarchivCardError("keine Route", 404, route_missing=True), "app_outdated"),
        (ZeitarchivCardError("kaputt", 500), "app_error"),
        (ZeitarchivCardError("kaputt", 503), "app_error"),
        (ZeitarchivCardError("voll", 429), "busy"),
        (ZeitarchivCardError("zu groß", 413), "too_large"),
        (ZeitarchivCardError("abgelehnt", 400), "invalid"),
        (ZeitarchivAuthError("abgelehnt"), "auth_failed"),
        (ZeitarchivApiError("weg"), "unreachable"),
    ],
)
async def test_failures_of_the_app_come_back_as_codes(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry,
    error: Exception, code: str,
) -> None:
    card_client.get_card_chart.side_effect = error
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7})
    assert response["success"] is False
    assert response["error"]["code"] == code
    # Ein Fehler landet nicht im Zwischenspeicher der Antworten. Abweisungen der App (400, 404, 413) merkt sich
    # die Integration einige Sekunden, damit dieselbe Frage die App nicht immer wieder belastet; danach, und
    # bei allen anderen Fehlern sofort, wird neu gefragt.
    card_client.get_card_chart.side_effect = None
    with patch("custom_components.zeitarchiv.card.time.monotonic", return_value=time.monotonic() + FAILURE_SECONDS + 1):
        again = await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7})
    assert again["success"] is True, again


async def test_an_app_without_the_capability_is_named(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["state"]})
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/items"})
    assert response["error"]["code"] == "app_outdated"
    card_client.get_card_items.assert_not_called()


async def test_without_a_connection_the_card_is_told_so(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Die Befehle gibt es, sobald die Integration geladen ist; ein Eintrag fehlt dafür nicht."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.config_entries.async_remove(config_entry.entry_id)
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/items"})
    assert response["error"]["code"] == "not_loaded"


async def test_the_card_files_are_served_and_announced(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    urls = hass.data[DATA_EXTRA_MODULE_URL]
    assert any(url.startswith("/zeitarchiv_card/zeitarchiv-card.js?v=") for url in urls)
    assert any(url.startswith("/zeitarchiv_card/zeitarchiv-sparkline.js?v=") for url in urls)
    client = await hass_client()
    for name in ("zeitarchiv-card.js", "zeitarchiv-sparkline.js", "chart-tile-render.js", "number-format.js", "tooltip-hold.js", "server-time.js", "html-escape.js", "state-entities.js", "table-compute.js", "table-tile-render.js", "table.css", "echarts.min.js", "catalog.json"):
        response = await client.get(f"/zeitarchiv_card/{name}")
        assert response.status == 200, name
    # Nur die ausgelieferten Dateien, nichts darüber hinaus.
    assert (await client.get("/zeitarchiv_card/../card.py")).status in (403, 404)
    assert (await client.get("/zeitarchiv_card/card.py")).status == 404


async def test_the_card_is_registered_once_for_several_entries(
    hass: HomeAssistant, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    before = len(hass.data[DATA_EXTRA_MODULE_URL])
    await card.async_setup_card(hass)
    assert len(hass.data[DATA_EXTRA_MODULE_URL]) == before


# --- Karte ohne gespeichertes Chart -----------------------------------------------------------

SERIES = {"spec_version": 1, "id": None, "name": None, "supported": True, "spec": {"entityIds": "[]"}, "data": {"series": []}}
ENTITIES = {"spec_version": 1, "entities": [{"entity_id": "sensor.a", "aggregation_type": "standard"}]}


@pytest.fixture
def series_client(card_client: MagicMock) -> Generator[MagicMock]:
    card_client.get_notices.return_value = {**NOTICES, "capabilities": ["cards", "card_series"]}
    card_client.get_card_series.return_value = SERIES
    card_client.get_card_entities.return_value = ENTITIES
    with (
        patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_series", card_client.get_card_series),
        patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_entities", card_client.get_card_entities),
    ):
        yield card_client


async def test_entities_and_a_series_are_passed_on_with_their_fixed_words(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    client = await hass_ws_client(hass)
    assert (await _call(client, {"type": "zeitarchiv/card/entities"}))["result"] == ENTITIES
    response = await _call(client, {"type": "zeitarchiv/card/series", "entity_ids": ["sensor.a", "sensor.b"], "period": "7d", "style": "percent"})
    assert response["success"] is True and response["result"] == SERIES
    series_client.get_card_series.assert_called_once_with(["sensor.a", "sensor.b"], "7d", "percent", None, 0)
    # Ohne Angaben gelten Monat und je Entität.
    await _call(client, {"type": "zeitarchiv/card/series", "entity_ids": ["sensor.a"]})
    series_client.get_card_series.assert_called_with(["sensor.a"], "month", "auto", None, 0)


@pytest.mark.parametrize(
    "arguments",
    [
        {"entity_ids": []},
        {"entity_ids": [f"sensor.x{n}" for n in range(11)]},
        {"entity_ids": ["sensor.a/../b"]},
        {"entity_ids": ["sensor.a,sensor.b"]},
        {"entity_ids": ["SENSOR.A"]},
        {"entity_ids": "sensor.a"},
        {"entity_ids": [5]},
        {"entity_ids": ["sensor.a"], "period": "jahrzehnt"},
        {"entity_ids": ["sensor.a"], "style": "bunt"},
        {"entity_ids": ["sensor.a"], "at": "gestern"},
        {},
    ],
)
async def test_a_series_takes_only_entity_ids_and_known_words(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry,
    arguments: dict[str, Any],
) -> None:
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/series", **arguments})
    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"
    series_client.get_card_series.assert_not_called()


async def test_other_users_may_not_ask_for_series_or_entities(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    series_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for message in ({"type": "zeitarchiv/card/entities"}, {"type": "zeitarchiv/card/series", "entity_ids": ["sensor.a"]}):
        assert (await _call(client, message))["error"]["code"] == "unauthorized"
    series_client.get_card_series.assert_not_called()
    series_client.get_card_entities.assert_not_called()


async def test_an_app_with_only_the_first_routes_is_named(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    """Gespeicherte Charts gehen (Fähigkeit "cards"), Entitäten direkt braucht "card_series"."""
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["cards"]})
    client = await hass_ws_client(hass)
    assert (await _call(client, {"type": "zeitarchiv/card/items"}))["success"] is True
    assert (await _call(client, {"type": "zeitarchiv/card/entities"}))["error"]["code"] == "app_outdated"
    response = await _call(client, {"type": "zeitarchiv/card/series", "entity_ids": ["sensor.a"]})
    assert response["error"]["code"] == "app_outdated"


@pytest.mark.parametrize(("status", "code"), [(400, "invalid"), (404, "not_found"), (429, "busy")])
async def test_refusals_of_the_app_for_a_series_come_back_as_codes(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry,
    status: int, code: str,
) -> None:
    series_client.get_card_series.side_effect = ZeitarchivCardError("nein", status)
    client = await hass_ws_client(hass)
    response = await _call(client, {"type": "zeitarchiv/card/series", "entity_ids": ["sensor.a"]})
    assert response["error"]["code"] == code


SPARK = {"spec_version": 1, "entity_id": "sensor.a", "range": "24h", "supported": True, "points": [[1, 2.0], [2, 3.0]]}


async def test_a_spark_is_passed_on_for_one_entity_and_a_known_range(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    series_client.get_notices.return_value = {**NOTICES, "capabilities": ["card_spark"]}
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["card_spark"]})
    series_client.get_card_spark = MagicMock(return_value=SPARK)
    client = await hass_ws_client(hass)
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_spark", series_client.get_card_spark):
        assert (await _call(client, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a", "range": "7d"}))["result"] == SPARK
        series_client.get_card_spark.assert_called_once_with("sensor.a", "7d")
        await _call(client, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.b"})
        series_client.get_card_spark.assert_called_with("sensor.b", "24h")


@pytest.mark.parametrize(
    "arguments",
    [{}, {"entity_id": "sensor.a/../b"}, {"entity_id": ["sensor.a"]}, {"entity_id": "sensor.a,sensor.b"}, {"entity_id": "sensor.a", "range": "1y"}],
)
async def test_a_spark_takes_one_id_and_a_known_range_only(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry,
    arguments: dict[str, Any],
) -> None:
    client = await hass_ws_client(hass)
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_spark") as ask:
        response = await _call(client, {"type": "zeitarchiv/card/spark", **arguments})
    assert response["error"]["code"] == "invalid_format"
    ask.assert_not_called()


async def test_a_spark_is_open_to_all_users_and_needs_an_app_that_knows_it(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    series_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["cards", "card_series"]})
    admin = await hass_ws_client(hass)
    assert (await _call(admin, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a"}))["error"]["code"] == "app_outdated"
    # Wer die Entität in HA sieht, liest ihren Verlauf dort ohnehin; die Sparkline ist nicht auf Administratoren beschränkt.
    other = await hass_ws_client(hass, hass_read_only_access_token)
    assert (await _call(other, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a"}))["error"]["code"] == "app_outdated"
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["cards", "card_spark"]})
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_spark", return_value=SPARK):
        assert (await _call(other, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a"}))["success"] is True


async def test_the_width_of_the_card_is_rounded_up_and_part_of_the_cache_key(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    client = await hass_ws_client(hass)
    await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7, "px": 431})
    card_client.get_card_chart.assert_called_with(7, None, 500)
    await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7, "px": 480})  # gleicher Schritt: aus dem Zwischenspeicher
    assert card_client.get_card_chart.call_count == 1
    await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7, "px": 1000})
    card_client.get_card_chart.assert_called_with(7, None, 1000)
    await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 8, "px": 4000})
    card_client.get_card_chart.assert_called_with(8, None, 4000)
    for bad in (-1, 4001, "100", 1.5):
        response = await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7, "px": bad})
        assert response["error"]["code"] == "invalid_format"


TABLE = {"spec_version": 1, "id": 4, "name": "Tabelle", "table": {"columns": [], "rows": [], "style": {}}, "query": {"columns": []}}


async def test_a_table_is_passed_on_by_whole_number_and_day_only(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["card_table"]})
    series_client.get_card_table = MagicMock(return_value=TABLE)
    client = await hass_ws_client(hass)
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_table", series_client.get_card_table):
        assert (await _call(client, {"type": "zeitarchiv/card/table", "table_id": 4, "at": "2026-10-01"}))["result"] == TABLE
        series_client.get_card_table.assert_called_once_with(4, "2026-10-01")
        await _call(client, {"type": "zeitarchiv/card/table", "table_id": 4, "at": "2026-10-01"})  # Zwischenspeicher
        assert series_client.get_card_table.call_count == 1
        for bad in ({}, {"table_id": 0}, {"table_id": "4"}, {"table_id": 4, "at": "gestern"}, {"table_id": 4.5}):
            response = await _call(client, {"type": "zeitarchiv/card/table", **bad})
            assert response["error"]["code"] == "invalid_format"
        assert series_client.get_card_table.call_count == 1


async def test_a_table_needs_a_share_for_other_users_and_an_app_that_knows_it(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    series_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["cards", "card_series", "card_spark"]})
    admin = await hass_ws_client(hass)
    assert (await _call(admin, {"type": "zeitarchiv/card/table", "table_id": 4}))["error"]["code"] == "app_outdated"
    other = await hass_ws_client(hass, hass_read_only_access_token)
    assert (await _call(other, {"type": "zeitarchiv/card/table", "table_id": 4}))["error"]["code"] == "unauthorized"



async def test_equal_asks_arriving_together_share_one_call_to_the_app(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    """Ein Dashboard mit mehreren Karten desselben Charts fragt die App einmal, nicht mehrfach."""
    import threading

    started = threading.Event()
    release = threading.Event()

    def slow(*_args, **_kwargs):
        started.set()
        release.wait(5)
        return CHART

    card_client.get_card_chart.side_effect = slow
    client = await hass_ws_client(hass)
    ids = []
    for _ in range(4):
        client.last_id = getattr(client, "last_id", 0) + 1
        ids.append(client.last_id)
        await client.send_json({"id": client.last_id, "type": "zeitarchiv/card/chart", "chart_id": 7})
    await hass.async_add_executor_job(started.wait, 5)
    release.set()
    answers = [await client.receive_json() for _ in ids]
    assert all(answer["success"] for answer in answers)
    assert card_client.get_card_chart.call_count == 1


async def test_different_asks_run_a_few_at_a_time_and_none_is_turned_away(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    """Die App erlaubt vier gleichzeitige Abfragen und antwortet sonst 429; die Integration lässt höchstens
    drei los und stellt den Rest an."""
    import threading
    import time

    from custom_components.zeitarchiv.card import MAX_APP_QUERIES

    lock = threading.Lock()
    running = {"now": 0, "most": 0}

    def tracked(*_args, **_kwargs):
        with lock:
            running["now"] += 1
            running["most"] = max(running["most"], running["now"])
        time.sleep(0.05)
        with lock:
            running["now"] -= 1
        return CHART

    card_client.get_card_chart.side_effect = tracked
    client = await hass_ws_client(hass)
    ids = []
    for chart_id in range(1, 11):
        client.last_id = getattr(client, "last_id", 0) + 1
        ids.append(client.last_id)
        await client.send_json({"id": client.last_id, "type": "zeitarchiv/card/chart", "chart_id": chart_id})
    answers = [await client.receive_json() for _ in ids]
    assert all(answer["success"] for answer in answers), [a for a in answers if not a["success"]]
    assert card_client.get_card_chart.call_count == 10
    assert 1 < running["most"] <= MAX_APP_QUERIES


async def test_a_user_cannot_fill_the_queue_in_front_of_the_administrators(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    series_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    """Normale Benutzer dürfen höchstens MAX_QUEUED_OTHERS Abfragen offen haben, der Rest bekommt sofort
    "beschäftigt"; ein Administrator wird trotzdem angenommen."""
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data(
        {**NOTICES, "capabilities": ["cards", "card_series", "card_spark"]}
    )
    release = threading.Event()
    running = threading.Semaphore(0)

    def slow(*_args, **_kwargs):
        running.release()
        release.wait(5)
        return SPARK

    other = await hass_ws_client(hass, hass_read_only_access_token)
    flood = 30
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_spark", side_effect=slow) as ask:
        for number in range(flood):
            other.last_id = getattr(other, "last_id", 0) + 1
            await other.send_json({"id": other.last_id, "type": "zeitarchiv/card/spark", "entity_id": f"sensor.s{number}"})
        # Die abgewiesenen Antworten kommen sofort; die angenommenen warten auf die App.
        refused = [await other.receive_json() for _ in range(flood - MAX_QUEUED_OTHERS)]
        assert {answer["error"]["code"] for answer in refused} == {"busy"}
        admin = await hass_ws_client(hass)
        admin.last_id = 0
        await admin.send_json({"id": 1, "type": "zeitarchiv/card/chart", "chart_id": 7})
        release.set()
        answers = [await other.receive_json() for _ in range(MAX_QUEUED_OTHERS)]
        assert all(answer["success"] for answer in answers)
        assert (await admin.receive_json())["success"] is True
        assert ask.call_count == MAX_QUEUED_OTHERS
    assert MAX_APP_QUERIES < MAX_QUEUED_OTHERS


async def test_a_refusal_of_the_app_is_remembered_for_a_few_seconds(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    """Dieselbe unbekannte Entität oder Tabelle soll die App nicht bei jeder Anfrage beschäftigen."""
    card_client.get_card_chart.side_effect = ZeitarchivCardError("weg", 404)
    client = await hass_ws_client(hass)
    for _ in range(3):
        assert (await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 9}))["error"]["code"] == "not_found"
    assert card_client.get_card_chart.call_count == 1
    # Nach der Frist wird neu gefragt; ein Fehler der App (5xx) oder ein 429 wird nie gemerkt.
    with patch("custom_components.zeitarchiv.card.time.monotonic", return_value=time.monotonic() + FAILURE_SECONDS + 1):
        await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 9})
    assert card_client.get_card_chart.call_count == 2
    card_client.get_card_chart.side_effect = ZeitarchivCardError("kaputt", 503)
    for _ in range(2):
        await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 10})
    assert card_client.get_card_chart.call_count == 4


async def test_a_malformed_id_or_day_is_refused_at_the_door(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    series_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    """Ein angehängter Zeilenumbruch oder fremde Ziffern gingen durch das Muster und endeten als unbekannter Fehler."""
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data(
        {**NOTICES, "capabilities": ["cards", "card_series", "card_spark", "card_table"]}
    )
    other = await hass_ws_client(hass, hass_read_only_access_token)
    admin = await hass_ws_client(hass)
    assert (await _call(other, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a\n"}))["error"]["code"] == "invalid_format"
    assert (await _call(admin, {"type": "zeitarchiv/card/series", "entity_ids": ["sensor.a\n"]}))["error"]["code"] == "invalid_format"
    for day in ("2026-10-01\n", "\u0662\u0660\u0662\u0666-10-01"):
        assert (await _call(admin, {"type": "zeitarchiv/card/chart", "chart_id": 7, "at": day}))["error"]["code"] == "invalid_format"


async def test_the_selection_survives_an_answer_of_the_app_without_lists(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    card_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    card_client.get_card_items.return_value = {"spec_version": 1, "items": None, "tables": None}
    for client in (await hass_ws_client(hass), await hass_ws_client(hass, hass_read_only_access_token)):
        response = await _call(client, {"type": "zeitarchiv/card/items"})
        assert response["success"] is True
        assert response["result"]["items"] == [] and response["result"]["tables"] == []


async def test_a_table_for_another_day_is_a_question_of_its_own(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, series_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data(
        {**NOTICES, "capabilities": ["cards", "card_series", "card_spark", "card_table"]}
    )
    admin = await hass_ws_client(hass)
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_card_table", return_value={"spec_version": 1}) as ask:
        await _call(admin, {"type": "zeitarchiv/card/table", "table_id": 4})
        await _call(admin, {"type": "zeitarchiv/card/table", "table_id": 4, "at": "2026-10-01"})
        await _call(admin, {"type": "zeitarchiv/card/table", "table_id": 4, "at": "2026-10-01"})
        assert ask.call_count == 2


async def test_waiting_asks_survive_the_connection_being_unloaded(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, card_client: MagicMock, loaded_entry: MockConfigEntry
) -> None:
    """Wer wartet, hat den Zugang zur App schon in der Hand; das Entladen darf ihn nicht in einen unbekannten
    Fehler werfen."""
    release = threading.Event()
    running = threading.Semaphore(0)

    def slow(*_args, **_kwargs):
        running.release()
        release.wait(5)
        return CHART

    card_client.get_card_chart.side_effect = slow
    admin = await hass_ws_client(hass)
    count = MAX_APP_QUERIES + 2
    for chart_id in range(1, count + 1):
        admin.last_id = getattr(admin, "last_id", 0) + 1
        await admin.send_json({"id": admin.last_id, "type": "zeitarchiv/card/chart", "chart_id": chart_id})
    for _ in range(MAX_APP_QUERIES):
        await hass.async_add_executor_job(running.acquire, True, 5)
    unload = hass.async_create_task(hass.config_entries.async_unload(loaded_entry.entry_id))
    await hass.async_block_till_done()
    release.set()
    answers = [await admin.receive_json() for _ in range(count)]
    await unload
    assert all(answer["success"] or answer["error"]["code"] != "unknown_error" for answer in answers), answers
