"""Lovelace-Karte: WebSocket-Befehle (nur Administratoren) und Auslieferung der Dateien."""

from __future__ import annotations

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
    assert response["result"] == ITEMS


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


async def test_other_users_may_not_ask(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    card_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for message in ({"type": "zeitarchiv/card/items"}, {"type": "zeitarchiv/card/chart", "chart_id": 7}):
        response = await _call(client, message)
        assert response["success"] is False
        assert response["error"]["code"] == "unauthorized"
    card_client.get_card_items.assert_not_called()
    card_client.get_card_chart.assert_not_called()


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
        (ZeitarchivCardError("voll", 429), "busy"),
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
    # Ein Fehler landet nicht im Zwischenspeicher.
    card_client.get_card_chart.side_effect = None
    assert (await _call(client, {"type": "zeitarchiv/card/chart", "chart_id": 7}))["success"] is True


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
    for name in ("zeitarchiv-card.js", "zeitarchiv-sparkline.js", "chart-tile-render.js", "number-format.js", "tooltip-hold.js", "server-time.js", "html-escape.js", "state-entities.js", "echarts.min.js", "catalog.json"):
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


async def test_a_spark_needs_an_admin_and_an_app_that_knows_it(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, hass_read_only_access_token: str,
    series_client: MagicMock, loaded_entry: MockConfigEntry,
) -> None:
    loaded_entry.runtime_data.notices_coordinator.async_set_updated_data({**NOTICES, "capabilities": ["cards", "card_series"]})
    admin = await hass_ws_client(hass)
    assert (await _call(admin, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a"}))["error"]["code"] == "app_outdated"
    other = await hass_ws_client(hass, hass_read_only_access_token)
    assert (await _call(other, {"type": "zeitarchiv/card/spark", "entity_id": "sensor.a"}))["error"]["code"] == "unauthorized"


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
