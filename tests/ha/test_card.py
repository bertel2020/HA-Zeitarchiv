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
    card_client.get_card_chart.assert_called_once_with(7, "2026-10-01")


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
    client = await hass_client()
    for name in ("zeitarchiv-card.js", "chart-tile-render.js", "number-format.js", "tooltip-hold.js", "server-time.js", "echarts.min.js", "catalog.json"):
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
