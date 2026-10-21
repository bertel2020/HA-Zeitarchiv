"""KI-Zugriff: die LLM-API, die Home Assistants MCP Server anbietet (ROADMAP 1.31).

Welche Werkzeuge es gibt, sagt die App über /api/ai/config; die Tests spielen
deren Antworten über einen Mock ein und prüfen, dass die API genau dann in
Home Assistant steht, wenn die App den Zugriff eingeschaltet hat."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import probatio
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeitarchiv.api import ZeitarchivApiError
from custom_components.zeitarchiv.const import DOMAIN

from .conftest import ENTRY_DATA, NOTICES


def _tool(name: str, app_tool: str, description: str = "Beschreibung") -> dict[str, Any]:
    return {
        "name": name, "app_tool": app_tool,
        "title": {"de": f"Titel {app_tool}", "en": f"Title {app_tool}"}, "description": description,
    }


CONFIG_ON = {
    "enabled": True,
    "config_rev": 1,
    "api_prompt": "Prompt der App",
    "tools": [
        _tool("zeitarchiv_search_entities", "search_entities"),
        _tool("zeitarchiv_get_summary", "get_summary", "Zusammenfassung"),
        _tool("zeitarchiv_get_series", "get_series"),
        _tool("zeitarchiv_compare_periods", "compare_periods"),
        _tool("zeitarchiv_get_notices", "get_notices"),
    ],
}
CONFIG_OFF = {"enabled": False, "config_rev": 2, "api_prompt": "", "tools": []}


def _context(language: str = "de") -> llm.LLMContext:
    return llm.LLMContext(
        platform="mcp_server", context=None, language=language, assistant="conversation", device_id=None
    )


def _zeitarchiv_apis(hass: HomeAssistant) -> list[llm.API]:
    return [api for api in llm.async_get_apis(hass) if api.id.startswith(f"{DOMAIN}_")]


def _notices(rev: int | None, caps: tuple[str, ...] = ("ai",)) -> dict:
    return {**NOTICES, "capabilities": list(caps), "ai_config_rev": rev}


@pytest.fixture
def ai_client(mock_client: MagicMock):
    """App mit KI-Fähigkeit, Zugriff eingeschaltet; ai_call ist der Weg zu /api/ai/*."""
    mock_client.get_notices.return_value = _notices(1)
    mock_client.get_ai_config.return_value = CONFIG_ON
    mock_client.ai_call.return_value = (200, {"matches": []})
    with (
        patch("custom_components.zeitarchiv.api.ZeitarchivClient.get_ai_config", mock_client.get_ai_config),
        patch("custom_components.zeitarchiv.api.ZeitarchivClient.ai_call", mock_client.ai_call),
    ):
        yield mock_client


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Ein weiterer Abruf von /api/notices, wie ihn der Koordinator jede Minute macht."""
    await entry.runtime_data.notices_coordinator.async_refresh()
    await hass.async_block_till_done()


async def _tools(hass: HomeAssistant, entry: MockConfigEntry, language: str = "de") -> dict[str, llm.Tool]:
    instance = await llm.async_get_api(hass, f"zeitarchiv_{entry.entry_id}", _context(language))
    return {tool.name: tool for tool in instance.tools}


async def _call(hass: HomeAssistant, entry: MockConfigEntry, name: str, args: dict) -> llm.ToolResult:
    """Ruft das Werkzeug direkt auf: APIInstance.async_call_tool() importiert die
    conversation-Komponente, und die braucht hassil, das hier fehlt."""
    tool = (await _tools(hass, entry))[name]
    return await tool.async_call(hass, llm.ToolInput(tool_name=name, tool_args=args), _context())


async def test_no_api_without_app_capability(hass: HomeAssistant, loaded_entry: MockConfigEntry, mock_client: MagicMock) -> None:
    assert _zeitarchiv_apis(hass) == []


async def test_api_registered_when_the_app_switches_it_on_and_removed_on_unload(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)

    [api] = _zeitarchiv_apis(hass)
    assert api.id == f"zeitarchiv_{unload_after_test.entry_id}"
    ai_client.get_ai_config.assert_called_once_with(api.id)

    assert await hass.config_entries.async_unload(unload_after_test.entry_id)
    await hass.async_block_till_done()
    assert unload_after_test.state is ConfigEntryState.NOT_LOADED
    assert _zeitarchiv_apis(hass) == []


async def test_not_registered_while_the_app_has_access_switched_off(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    ai_client.get_ai_config.return_value = CONFIG_OFF
    await _setup(hass, unload_after_test)
    assert _zeitarchiv_apis(hass) == []


async def test_tools_and_texts_come_from_the_app_config(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    instance = await llm.async_get_api(hass, f"zeitarchiv_{unload_after_test.entry_id}", _context("de"))
    assert instance.api_prompt == "Prompt der App"
    tools = {tool.name: tool for tool in instance.tools}
    assert set(tools) == {tool["name"] for tool in CONFIG_ON["tools"]}
    assert tools["zeitarchiv_get_summary"].description == "Zusammenfassung"
    assert tools["zeitarchiv_get_summary"].title == "Titel get_summary"
    for tool in tools.values():
        assert tool.annotations.read_only and not tool.annotations.destructive
        assert tool.integration == DOMAIN

    schema = probatio.to_openapi(tools["zeitarchiv_get_series"].parameters)
    assert schema["required"] == ["entity_ids", "period"]
    assert schema["properties"]["metric"]["enum"] == ["avg", "min", "max", "total"]
    assert schema["properties"]["entity_ids"]["maxItems"] == 3

    english = await _tools(hass, unload_after_test, "en-GB")
    assert english["zeitarchiv_get_summary"].title == "Title get_summary"
    other = await _tools(hass, unload_after_test, "fr")
    assert other["zeitarchiv_get_summary"].title == "Title get_summary"


async def test_switching_off_and_on_again_follows_the_config_rev(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    assert len(_zeitarchiv_apis(hass)) == 1

    ai_client.get_notices.return_value = _notices(2)
    ai_client.get_ai_config.return_value = CONFIG_OFF
    await _poll(hass, unload_after_test)
    assert _zeitarchiv_apis(hass) == []

    ai_client.get_notices.return_value = _notices(3)
    ai_client.get_ai_config.return_value = CONFIG_ON
    await _poll(hass, unload_after_test)
    assert len(_zeitarchiv_apis(hass)) == 1


async def test_changed_texts_apply_without_re_registering(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    [api] = _zeitarchiv_apis(hass)

    changed = {**CONFIG_ON, "config_rev": 2, "tools": [_tool("zeitarchiv_get_notices", "get_notices", "Neuer Text")]}
    ai_client.get_notices.return_value = _notices(2)
    ai_client.get_ai_config.return_value = changed
    await _poll(hass, unload_after_test)

    assert _zeitarchiv_apis(hass) == [api]
    tools = await _tools(hass, unload_after_test)
    assert list(tools) == ["zeitarchiv_get_notices"] and tools["zeitarchiv_get_notices"].description == "Neuer Text"


async def test_unchanged_rev_does_not_fetch_the_config_again(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    await _poll(hass, unload_after_test)
    await _poll(hass, unload_after_test)
    assert ai_client.get_ai_config.call_count == 1


async def test_app_losing_the_capability_removes_the_api(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    ai_client.get_notices.return_value = _notices(None, caps=())
    await _poll(hass, unload_after_test)
    assert _zeitarchiv_apis(hass) == []


async def test_failed_config_fetch_is_retried_with_the_next_poll(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    ai_client.get_ai_config.side_effect = ZeitarchivApiError("down")
    await _setup(hass, unload_after_test)
    assert _zeitarchiv_apis(hass) == []

    ai_client.get_ai_config.side_effect = None
    await _poll(hass, unload_after_test)
    assert len(_zeitarchiv_apis(hass)) == 1


async def test_tools_the_integration_does_not_know_are_skipped(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    ai_client.get_ai_config.return_value = {
        **CONFIG_ON, "tools": [_tool("zeitarchiv_zukunft", "future_tool"), _tool("zeitarchiv_get_notices", "get_notices")],
    }
    await _setup(hass, unload_after_test)
    assert list(await _tools(hass, unload_after_test)) == ["zeitarchiv_get_notices"]


async def test_tool_call_passes_arguments_and_returns_the_app_answer(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    ai_client.ai_call.return_value = (200, {"results": [{"entity_id": "sensor.a"}]})

    result = await _call(
        hass, unload_after_test, "zeitarchiv_compare_periods",
        {"entity_ids": ["sensor.a"], "period": "month", "compare_to": "previous_period"},
    )

    assert result.error is False and result.data == {"results": [{"entity_id": "sensor.a"}]}
    ai_client.ai_call.assert_called_once_with(
        "compare_periods", {"entity_ids": ["sensor.a"], "period": "month", "compare_to": "previous_period"}, None
    )


async def test_app_errors_reach_the_model_as_error_results(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    call = (hass, unload_after_test, "zeitarchiv_search_entities", {})

    ai_client.ai_call.return_value = (403, {"error": "ai_disabled", "message": "AI access is switched off."})
    switched_off = await _call(*call)
    assert switched_off.error is True and switched_off.data["error"] == "ai_disabled"

    ai_client.ai_call.return_value = (429, {"error": "busy", "message": "Too many requests."})
    assert (await _call(*call)).data["error"] == "busy"

    ai_client.ai_call.side_effect = ZeitarchivApiError("down")
    unreachable = await _call(*call)
    assert unreachable.error is True and unreachable.data["error"] == "archive_unreachable"


async def test_invalid_arguments_are_rejected_before_the_app(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    with pytest.raises(probatio.Invalid):
        await _call(hass, unload_after_test, "zeitarchiv_get_series", {"entity_ids": list("abcd"), "period": "day"})
    with pytest.raises(probatio.Invalid):
        await _call(hass, unload_after_test, "zeitarchiv_compare_periods", {"entity_ids": ["a"], "period": "hour"})
    ai_client.ai_call.assert_not_called()


async def test_two_connections_get_distinct_namespaced_tools(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    second = MockConfigEntry(
        domain=DOMAIN, version=2, title="Zeitarchiv (Test)", data={**ENTRY_DATA, "host": "test.local"},
    )
    second.add_to_hass(hass)
    # Das Einrichten der Domain lädt beide Einträge.
    await _setup(hass, unload_after_test)
    assert second.state is ConfigEntryState.LOADED

    ids = [api.id for api in _zeitarchiv_apis(hass)]
    assert len(ids) == 2
    assert {call.args[0] for call in ai_client.get_ai_config.call_args_list} == set(ids)
    merged = await llm.async_get_api(hass, ids, _context())
    names = [tool.name for tool in merged.tools]
    assert len(names) == len(set(names)) == 2 * len(CONFIG_ON["tools"])

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()


async def test_the_account_kind_is_sent_to_the_app(
    hass: HomeAssistant, ai_client: MagicMock, unload_after_test: MockConfigEntry
) -> None:
    await _setup(hass, unload_after_test)
    admin = await hass.auth.async_create_user("Chef", group_ids=["system-admin"])
    member = await hass.auth.async_create_user("Gast", group_ids=["system-users"])
    tool = (await _tools(hass, unload_after_test))["zeitarchiv_get_notices"]

    for user, expected in ((admin, "admin"), (member, "user"), (None, None)):
        ai_client.ai_call.reset_mock()
        context = Context(user_id=user.id) if user else None
        llm_context = llm.LLMContext(
            platform="mcp_server", context=context, language="de", assistant="conversation", device_id=None
        )
        await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args={}), llm_context)
        ai_client.ai_call.assert_called_once_with("get_notices", {}, expected)
