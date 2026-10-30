"""Lovelace-Karte: gespeicherte Zeitarchiv-Charts im Dashboard.

Die Karte (frontend/zeitarchiv-card.js) spricht nie mit der App, sondern nur mit
Home Assistant: zwei WebSocket-Befehle, die diese Datei bereitstellt und die den
Token der Verbindung serverseitig behalten. Dahinter stehen /api/card/items und
/api/card/chart der App.

Nur Administratoren: Jeder angemeldete Benutzer könnte sonst jedes gespeicherte
Chart über seine ID abfragen, und Home Assistant kennt keine Rechte je Chart.
Die Befehle nehmen deshalb ausschließlich eine ganzzahlige Chart-ID (und einen
Stichtag) an und bauen den Pfad selbst; nie reicht die Integration einen frei
wählbaren Pfad oder Parameter an die App durch, sonst wäre sie ein Proxy an der
Whitelist des Token-Ports vorbei.

Die Karte liefert diese Integration mit aus (statischer Pfad plus
add_extra_js_url), eine Ressource muss niemand eintragen. Ihr Zeichencode ist
der der Dashboard-Kacheln der App; frontend/ enthält unveränderte Kopien.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import probatio
from homeassistant.components import websocket_api
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .api import (
    ZeitarchivApiError,
    ZeitarchivAuthError,
    ZeitarchivCardError,
    CARD_MAX_ENTITIES,
    CARD_PERIODS,
    CARD_SPARK_RANGES,
    CARD_STYLES,
    capabilities_from,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/zeitarchiv_card"
FRONTEND_DIR = Path(__file__).parent / "frontend"
CARD_FILE = "zeitarchiv-card.js"
SPARKLINE_FILE = "zeitarchiv-sparkline.js"

#: Wie lange eine Antwort der App für weitere Karten und Betrachter gilt. Mehrere
#: Karten oder Browser, die dasselbe Chart zeigen, fragen die App nur einmal.
CACHE_SECONDS = 30.0
CACHE_MAX_ENTRIES = 64

_CACHE_KEY = f"{DOMAIN}_card_cache"

# Die Codes sind der Vertrag mit der Karte (sie übersetzt sie selbst).
ERROR_NOT_LOADED = "not_loaded"
ERROR_APP_OUTDATED = "app_outdated"
ERROR_NOT_FOUND = "not_found"
ERROR_BUSY = "busy"
ERROR_AUTH = "auth_failed"
ERROR_UNREACHABLE = "unreachable"
ERROR_INVALID = "invalid"

_DAY = r"^\d{4}-\d{2}-\d{2}$"
_ENTITY = r"^[a-z0-9_]+\.[a-z0-9_]+$"


async def async_setup_card(hass: HomeAssistant) -> None:
    """Meldet Befehle und Karte einmal je Home Assistant an (nicht je Eintrag)."""
    if _CACHE_KEY in hass.data:
        return
    # http und websocket_api stehen nur in after_dependencies (die Reihenfolge,
    # ohne sie zu erzwingen): ohne Webserver gibt es keine Karte, die Integration
    # läuft trotzdem.
    if getattr(hass, "http", None) is None:
        _LOGGER.debug("Kein Webserver, Zeitarchiv-Karte wird nicht angemeldet")
        return
    hass.data[_CACHE_KEY] = {}
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(FRONTEND_DIR), True)])
    # Das Frontend ist bewusst keine harte Abhängigkeit (after_dependencies
    # sichert nur die Reihenfolge): wer es abgeschaltet hat, braucht auch keine
    # Karte, und die Integration läuft trotzdem.
    if DATA_EXTRA_MODULE_URL in hass.data:
        # Die Fassung hängt an jeder Datei, auch an denen, die die Karte nachlädt
        # (siehe zeitarchiv-card.js): ein Update ersetzt sie ohne Browser-Cache.
        add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILE}?v={integration.version}")
        add_extra_js_url(hass, f"{URL_BASE}/{SPARKLINE_FILE}?v={integration.version}")
    else:
        _LOGGER.debug("Home-Assistant-Frontend nicht geladen, Zeitarchiv-Karte wird nicht angemeldet")
    websocket_api.async_register_command(hass, ws_card_items)
    websocket_api.async_register_command(hass, ws_card_chart)
    websocket_api.async_register_command(hass, ws_card_entities)
    websocket_api.async_register_command(hass, ws_card_series)
    websocket_api.async_register_command(hass, ws_card_spark)


def _entry(hass: HomeAssistant, entry_id: str | None):
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id is not None:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    return entries[0] if entries else None


def _cached(hass: HomeAssistant, key: tuple) -> dict[str, Any] | None:
    hit = hass.data[_CACHE_KEY].get(key)
    if hit is None or time.monotonic() - hit[0] > CACHE_SECONDS:
        return None
    return hit[1]


def _remember(hass: HomeAssistant, key: tuple, value: dict[str, Any]) -> None:
    cache = hass.data[_CACHE_KEY]
    now = time.monotonic()
    for old in [k for k, (stamp, _) in cache.items() if now - stamp > CACHE_SECONDS]:
        del cache[old]
    while len(cache) >= CACHE_MAX_ENTRIES:
        del cache[min(cache, key=lambda k: cache[k][0])]
    cache[key] = (now, value)


async def _fetch(
    hass: HomeAssistant, connection, msg: dict[str, Any], key: tuple, call, capability: str = "cards",
) -> None:
    """Gemeinsamer Ablauf beider Befehle: Verbindung wählen, Fähigkeit prüfen,
    zwischengespeicherte Antwort oder Abruf in der App, Fehler als Code."""
    entry = _entry(hass, msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], ERROR_NOT_LOADED, "Keine Zeitarchiv-Verbindung eingerichtet")
        return
    runtime = entry.runtime_data
    notices = runtime.notices_coordinator.data
    # Ohne Antwort der App (gerade gestartet) bleibt die Fähigkeit unbekannt;
    # dann entscheidet die Antwort selbst.
    if notices and capability not in capabilities_from(notices):
        connection.send_error(msg["id"], ERROR_APP_OUTDATED, "Die Zeitarchiv-App ist zu alt für die Karte")
        return
    key = (entry.entry_id, *key)
    result = _cached(hass, key)
    if result is None:
        try:
            result = await hass.async_add_executor_job(call, runtime.client)
        except ZeitarchivAuthError:
            connection.send_error(msg["id"], ERROR_AUTH, "Zugangsdaten von der App abgelehnt")
            return
        except ZeitarchivCardError as err:
            if err.status == 429:
                connection.send_error(msg["id"], ERROR_BUSY, "Zeitarchiv ist gerade beschäftigt")
            elif err.status == 400:
                connection.send_error(msg["id"], ERROR_INVALID, "Die Angaben der Karte hat die App abgelehnt")
            else:
                connection.send_error(msg["id"], ERROR_NOT_FOUND, "Chart oder Entität nicht gefunden")
            return
        except ZeitarchivApiError as err:
            _LOGGER.debug("Karte: Abruf in der App fehlgeschlagen: %s", err)
            connection.send_error(msg["id"], ERROR_UNREACHABLE, "Zeitarchiv nicht erreichbar")
            return
        _remember(hass, key, result)
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {"type": "zeitarchiv/card/items", probatio.Optional("entry_id"): str}
)
@websocket_api.async_response
async def ws_card_items(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Gespeicherte Charts für den Editor der Karte."""
    await _fetch(hass, connection, msg, ("items",), lambda client: client.get_card_items())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "zeitarchiv/card/chart",
        probatio.Required("chart_id"): probatio.All(int, probatio.Range(min=1)),
        probatio.Optional("at"): probatio.All(str, probatio.Match(_DAY)),
        probatio.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_card_chart(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Einstellungen und Daten eines gespeicherten Charts."""
    chart_id, at = msg["chart_id"], msg.get("at")
    await _fetch(hass, connection, msg, ("chart", chart_id, at), lambda client: client.get_card_chart(chart_id, at))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {"type": "zeitarchiv/card/entities", probatio.Optional("entry_id"): str}
)
@websocket_api.async_response
async def ws_card_entities(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Archivierte Entitäten für die Auswahl der Karte ohne gespeichertes Chart."""
    await _fetch(
        hass, connection, msg, ("entities",), lambda client: client.get_card_entities(), capability="card_series",
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "zeitarchiv/card/series",
        probatio.Required("entity_ids"): probatio.All(
            [probatio.All(str, probatio.Match(_ENTITY))], probatio.Length(min=1, max=CARD_MAX_ENTITIES)
        ),
        probatio.Optional("period", default="month"): probatio.In(CARD_PERIODS),
        probatio.Optional("style", default="auto"): probatio.In(CARD_STYLES),
        probatio.Optional("at"): probatio.All(str, probatio.Match(_DAY)),
        probatio.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_card_series(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Einstellungen und Daten für frei gewählte Entitäten."""
    ids, period, style, at = list(msg["entity_ids"]), msg["period"], msg["style"], msg.get("at")
    await _fetch(
        hass, connection, msg, ("series", tuple(ids), period, style, at),
        lambda client: client.get_card_series(ids, period, style, at), capability="card_series",
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "zeitarchiv/card/spark",
        probatio.Required("entity_id"): probatio.All(str, probatio.Match(_ENTITY)),
        probatio.Optional("range", default="24h"): probatio.In(CARD_SPARK_RANGES),
        probatio.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_card_spark(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Kurze Reihe einer Entität für die Sparkline unter einer Kachelkarte."""
    entity_id, range_key = msg["entity_id"], msg["range"]
    await _fetch(
        hass, connection, msg, ("spark", entity_id, range_key),
        lambda client: client.get_card_spark(entity_id, range_key), capability="card_spark",
    )
