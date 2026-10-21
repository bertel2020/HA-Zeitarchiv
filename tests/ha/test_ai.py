"""KI-Zugriff: die LLM-API, die Home Assistants MCP Server anbietet (ROADMAP 1.31)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import probatio
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.api import ZeitarchivApiError
from custom_components.zeitarchiv.const import DOMAIN

from .conftest import ENTRY_DATA


def _context(language: str = "de") -> llm.LLMContext:
    return llm.LLMContext(
        platform="mcp_server", context=None, language=language, assistant="conversation", device_id=None
    )


def _zeitarchiv_apis(hass: HomeAssistant) -> list[llm.API]:
    return [api for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}_")]


async def _call(hass: HomeAssistant, entry: MockConfigEntry, name: str, args: dict) -> llm.ToolResult:
    """Ruft das Werkzeug direkt auf: APIInstance.async_call_tool() importiert
    die conversation-Komponente, und die braucht hassil, das hier fehlt."""
    instance = await llm.async_get_api(hass, f"zeitarchiv_{entry.entry_id}", _context())
    tool = next(tool for tool in instance.tools if tool.name == name)
    return await tool.async_call(hass, llm.ToolInput(tool_name=name, tool_args=args), _context())


@pytest.fixture
def ai_client(mock_client: MagicMock):
    """App mit Fähigkeit "ai"; ai_call ist der einzige Weg zu /api/ai/*."""
    mock_client.test_connection.return_value = frozenset({"ai"})
    mock_client.ai_call.return_value = (200, {"matches": []})
    with patch("custom_components.zeitarchiv.api.ZeitarchivClient.ai_call", mock_client.ai_call):
        yield mock_client


async def test_no_api_without_app_capability(hass: HomeAssistant, loaded_entry: MockConfigEntry) -> None:
    assert _zeitarchiv_apis(hass) == []


async def test_api_registered_per_entry_and_removed_on_unload(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()

    [api] = _zeitarchiv_apis(hass)
    assert api.id == f"zeitarchiv_{unload_after_test.entry_id}"
    assert api.name == "Zeitarchiv (Zeitarchiv (Produktivsystem))"

    assert await hass.config_entries.async_unload(unload_after_test.entry_id)
    await hass.async_block_till_done()
    assert unload_after_test.state is ConfigEntryState.NOT_LOADED
    assert _zeitarchiv_apis(hass) == []


async def test_tools_are_read_only_with_titles_and_schemas(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()

    instance = await llm.async_get_api(hass, f"zeitarchiv_{unload_after_test.entry_id}", _context("de"))
    tools = {tool.name: tool for tool in instance.tools}
    assert set(tools) == {"zeitarchiv_search_entities", "zeitarchiv_get_summary"}
    assert tools["zeitarchiv_get_summary"].title == "Zeitarchiv: Zeitraum auswerten"
    for tool in tools.values():
        assert tool.annotations.read_only and not tool.annotations.destructive
        assert tool.integration == DOMAIN
        assert "search_entities" in tool.description or tool is tools["zeitarchiv_search_entities"]

    schema = probatio.to_openapi(tools["zeitarchiv_get_summary"].parameters)
    assert schema["required"] == ["entity_ids", "period"]
    assert schema["properties"]["period"]["enum"][0] == "hour"

    english = await llm.async_get_api(hass, f"zeitarchiv_{unload_after_test.entry_id}", _context("en-GB"))
    assert english.tools[1].title == "Zeitarchiv: Summarize a period"


async def test_tool_call_passes_arguments_and_returns_the_app_answer(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    ai_client.ai_call.return_value = (200, {"results": [{"entity_id": "sensor.a"}]})
    result = await _call(
        hass, unload_after_test, "zeitarchiv_get_summary",
        {"entity_ids": ["sensor.a"], "period": "month", "date": "2025-10-03"},
    )

    assert result.error is False
    assert result.data == {"results": [{"entity_id": "sensor.a"}]}
    ai_client.ai_call.assert_called_once_with(
        "get_summary", {"entity_ids": ["sensor.a"], "period": "month", "date": "2025-10-03"}
    )


async def test_app_errors_reach_the_model_as_error_results(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    call = (hass, unload_after_test, "zeitarchiv_search_entities", {})

    ai_client.ai_call.return_value = (403, {"error": "ai_disabled", "message": "AI access is switched off."})
    switched_off = await _call(*call)
    assert switched_off.error is True and switched_off.data["error"] == "ai_disabled"

    ai_client.ai_call.side_effect = ZeitarchivApiError("down")
    unreachable = await _call(*call)
    assert unreachable.error is True and unreachable.data["error"] == "archive_unreachable"


async def test_invalid_arguments_are_rejected_before_the_app(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(probatio.Invalid):
        await _call(hass, unload_after_test, "zeitarchiv_get_summary", {"entity_ids": ["sensor.a"], "period": "fortnight"})
    ai_client.ai_call.assert_not_called()


async def test_two_connections_get_distinct_namespaced_tools(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    second = MockConfigEntry(
        domain=DOMAIN, version=2, title="Zeitarchiv (Test)", data={**ENTRY_DATA, "host": "test.local"},
    )
    second.add_to_hass(hass)
    # Das Einrichten der Domain lädt beide Einträge.
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.LOADED

    ids = [api.id for api in _zeitarchiv_apis(hass)]
    assert len(ids) == 2
    merged = await llm.async_get_api(hass, ids, _context())
    names = [tool.name for tool in merged.tools]
    assert len(names) == len(set(names)) == 4

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
