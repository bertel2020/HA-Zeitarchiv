"""KI-Zugriff: Zeitarchiv als LLM-API von Home Assistant (ROADMAP 1.31).

Home Assistants "MCP Server" findet jede mit llm.async_register_api()
angemeldete API und bietet sie Claude, ChatGPT & Co. an (OAuth und
Fernzugriff übernimmt HA). Diese Datei ist nur die dünne Hülle: Gerechnet
wird in der App.

Was angeboten wird, bestimmt die App. Sie meldet über GET /api/ai/config, ob
der KI-Zugriff eingeschaltet ist, welche Werkzeuge sie anbietet und mit welchen
Titeln und Beschreibungen. Die Integration kennt nur die Parameter-Schemata
(den Vertrag mit der App), nicht die Texte: Beschreibungen lassen sich so ohne
neue Integrationsversion verbessern, und ein ausgeschalteter Zugriff nimmt die
API wieder aus HA heraus.

Braucht Home Assistant 2026.10 (probatio-Schemas, ToolResult, annotations).
Ältere Versionen importieren dieses Modul nicht erfolgreich — __init__.py
fängt das ab und meldet einmal einen Hinweis, statt Kompatibilitätscode für
voluptuous mitzuschleppen.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm

from .api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivClient, capabilities_from
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_PERIODS = ["hour", "day", "week", "month", "year", "decade"]
_ENTITY_IDS_10 = probatio.All([str], probatio.Length(min=1, max=10))

#: Parameter-Schemata je Werkzeug der App. Das ist der Vertrag mit den Routen in
#: app/ai_routes.py; ein Werkzeug, das die App meldet und hier fehlt (neuere App),
#: wird übersprungen.
SCHEMAS: dict[str, probatio.Schema] = {
    "search_entities": probatio.Schema({
        probatio.Optional("query"): str,
        probatio.Optional("type"): probatio.In(["counter", "standard", "switch", "state"]),
        probatio.Optional("unit"): str,
        probatio.Optional("limit"): probatio.All(int, probatio.Range(min=1, max=50)),
    }),
    "get_summary": probatio.Schema({
        probatio.Required("entity_ids"): _ENTITY_IDS_10,
        probatio.Required("period"): probatio.In(_PERIODS),
        probatio.Optional("date"): str,
        probatio.Optional("rolling"): bool,
    }),
    "get_series": probatio.Schema({
        probatio.Required("entity_ids"): probatio.All([str], probatio.Length(min=1, max=3)),
        probatio.Required("period"): probatio.In(_PERIODS),
        probatio.Optional("date"): str,
        probatio.Optional("rolling"): bool,
        probatio.Optional("metric"): probatio.In(["avg", "min", "max", "total"]),
    }),
    "compare_periods": probatio.Schema({
        probatio.Required("entity_ids"): _ENTITY_IDS_10,
        probatio.Required("period"): probatio.In(_PERIODS[1:]),
        probatio.Optional("date"): str,
        probatio.Optional("compare_to"): str,
        probatio.Optional("same_elapsed"): bool,
    }),
    "get_energy_overview": probatio.Schema({
        probatio.Required("period"): probatio.In(["day", "month", "year"]),
        probatio.Optional("date"): str,
    }),
    "get_notices": probatio.Schema({}),
}

_ANNOTATIONS = llm.ToolAnnotations(
    read_only=True, destructive=False, idempotent=True, open_world=False
)


class ZeitarchivTool(llm.Tool):
    """Ein Werkzeug der App: Argumente prüfen, dort ausführen, Antwort durchreichen."""

    annotations = _ANNOTATIONS
    integration = DOMAIN

    def __init__(
        self, client: ZeitarchivClient, *, name: str, app_tool: str, title: str, description: str,
    ) -> None:
        self._client = client
        self.name = name
        self.app_tool = app_tool
        self.title = title
        self.description = description
        self.parameters = SCHEMAS[app_tool]

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        arguments = self.parameters(tool_input.tool_args)
        account = await _account_kind(hass, llm_context)
        try:
            status, body = await hass.async_add_executor_job(self._client.ai_call, self.app_tool, arguments, account)
        except ZeitarchivAuthError:
            return _error("unauthorized", "Zeitarchiv rejected the API token; the user must renew it in Home Assistant.")
        except ZeitarchivApiError as err:
            _LOGGER.warning("Zeitarchiv-Abfrage fehlgeschlagen: %s", err)
            return _error("archive_unreachable", "The Zeitarchiv app did not answer; try again later.")
        return llm.ToolResult(data=body, error=status >= 400)


async def _account_kind(hass: HomeAssistant, llm_context: llm.LLMContext) -> str | None:
    """"admin" oder "user", je nach Konto, mit dem der Client angemeldet ist.
    None, wenn die Anfrage kein Konto trägt (etwa ein lokaler Gesprächsagent)."""
    user_id = llm_context.context.user_id if llm_context.context else None
    if not user_id:
        return None
    user = await hass.auth.async_get_user(user_id)
    if user is None:
        return None
    return "admin" if user.is_admin else "user"


def _error(code: str, message: str) -> llm.ToolResult:
    return llm.ToolResult(data={"error": code, "message": message}, error=True)


def api_id(entry: ConfigEntry) -> str:
    return f"{DOMAIN}_{entry.entry_id}"


def _language_key(language: str | None) -> str:
    return (language or "en").split("-")[0]


class ZeitarchivApi(llm.API):
    """Eine API je Verbindung; jede hat ihre eigene MCP-URL /api/mcp/<id>.

    Die Werkzeuge entstehen bei jedem Abruf aus der zuletzt gemeldeten
    Konfiguration der App (APIInstance wird pro Anfrage gebaut). Ändert die App
    Texte oder die Auswahl, genügt es, die Konfiguration zu ersetzen."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ZeitarchivClient) -> None:
        super().__init__(hass=hass, id=api_id(entry), name=f"Zeitarchiv ({entry.title})")
        self._client = client
        self.config: dict[str, Any] = {}

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        language = _language_key(llm_context.language or self.hass.config.language)
        tools = []
        for item in self.config.get("tools", []):
            app_tool = item.get("app_tool")
            if app_tool not in SCHEMAS or not isinstance(item.get("name"), str):
                continue
            titles = item.get("title") if isinstance(item.get("title"), dict) else {}
            tools.append(ZeitarchivTool(
                self._client,
                name=item["name"],
                app_tool=app_tool,
                title=titles.get(language) or titles.get("en") or item["name"],
                description=str(item.get("description") or ""),
            ))
        return llm.APIInstance(
            api=self, api_prompt=str(self.config.get("api_prompt") or ""), llm_context=llm_context, tools=tools,
        )


class ZeitarchivAiManager:
    """Hält die LLM-API einer Verbindung im Takt mit dem Schalter der App.

    Angemeldet ist sie genau dann, wenn die App die Fähigkeit "ai" meldet UND
    den Zugriff eingeschaltet hat. Jede Änderung an den Einstellungen zählt
    ``ai_config_rev`` hoch, das /api/notices im Minutentakt mitliefert; ändert
    sich der Wert, holt der Manager die Konfiguration neu. Ein Umschalten wirkt
    so ohne Neustart von Home Assistant."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ZeitarchivClient) -> None:
        self._hass = hass
        self._entry = entry
        self._client = client
        self._api: ZeitarchivApi | None = None
        self._unregister: Callable[[], None] | None = None
        self._rev: int | None = None
        self._busy = False

    @property
    def registered(self) -> bool:
        return self._unregister is not None

    @callback
    def handle_notices(self, data: dict | None) -> None:
        """Koordinator-Listener: entscheidet, ob die Konfiguration neu zu holen ist."""
        if not data or data.get("unauthenticated"):
            return
        if "ai" not in capabilities_from(data):
            self._drop()
            self._rev = None
            return
        rev = data.get("ai_config_rev")
        if self._rev is not None and rev == self._rev:
            return
        if self._busy:
            return
        self._busy = True
        self._entry.async_create_background_task(
            self._hass, self._async_refresh(rev), f"{DOMAIN}_ai_config_{self._entry.entry_id}"
        )

    async def _async_refresh(self, rev: int | None) -> None:
        try:
            config = await self._hass.async_add_executor_job(self._client.get_ai_config, api_id(self._entry))
        except ZeitarchivAuthError:
            _LOGGER.debug("KI-Konfiguration: Token abgelehnt, nächster Versuch bei der nächsten Meldung")
            return
        except ZeitarchivApiError as err:
            # _rev bleibt unverändert: Der nächste Abruf von /api/notices versucht es erneut.
            _LOGGER.debug("KI-Konfiguration nicht abrufbar: %s", err)
            return
        finally:
            self._busy = False
        self._rev = rev if rev is not None else config.get("config_rev")
        if config.get("enabled") is True and isinstance(config.get("tools"), list) and config["tools"]:
            self._apply(config)
        else:
            self._drop()

    def _apply(self, config: dict[str, Any]) -> None:
        if self._api is None:
            self._api = ZeitarchivApi(self._hass, self._entry, self._client)
        self._api.config = config
        if self._unregister is None:
            self._unregister = llm.async_register_api(self._hass, self._api)
            _LOGGER.info("Zeitarchiv-KI-Zugriff angemeldet · API=%s", self._api.id)

    def _drop(self) -> None:
        if self._unregister is not None:
            self._unregister()
            self._unregister = None
            _LOGGER.info("Zeitarchiv-KI-Zugriff abgemeldet · API=%s", api_id(self._entry))

    @callback
    def async_shutdown(self) -> None:
        self._drop()
