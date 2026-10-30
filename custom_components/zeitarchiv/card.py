"""Lovelace-Karte: gespeicherte Zeitarchiv-Charts im Dashboard.

Die Karte (frontend/zeitarchiv-card.js) spricht nie mit der App, sondern nur mit
Home Assistant: zwei WebSocket-Befehle, die diese Datei bereitstellt und die den
Token der Verbindung serverseitig behalten. Dahinter stehen /api/card/items und
/api/card/chart der App.

Standardmäßig nur Administratoren: Jeder angemeldete Benutzer könnte sonst jedes
gespeicherte Chart über seine ID abfragen, und Home Assistant kennt keine Rechte je
Chart. Was ein Administrator in den Optionen unter "Karte freigeben" benennt, sehen
auch andere Benutzer (Wandtablets, Familienkonten). Die Sparkline unter einer Kachelkarte
dürfen alle Benutzer abrufen: wer eine Entität in Home Assistant sieht, kann ihren Verlauf
dort ohnehin lesen (History-API, ohne Administratorrechte). Entitäten direkt bleiben
Administratoren vorbehalten. Die Befehle nehmen deshalb ausschließlich eine ganzzahlige Chart-ID (und einen
Stichtag) an und bauen den Pfad selbst; nie reicht die Integration einen frei
wählbaren Pfad oder Parameter an die App durch, sonst wäre sie ein Proxy an der
Whitelist des Token-Ports vorbei.

Die Karte liefert diese Integration mit aus (statischer Pfad plus
add_extra_js_url), eine Ressource muss niemand eintragen. Ihr Zeichencode ist
der der Dashboard-Kacheln der App; frontend/ enthält unveränderte Kopien.
"""

from __future__ import annotations

import asyncio
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
    CARD_MAX_PX,
    CARD_PERIODS,
    CARD_SPARK_RANGES,
    CARD_STYLES,
    capabilities_from,
)
from .const import CONF_CARD_SHARED_CHARTS, CONF_CARD_SHARED_TABLES, DOMAIN

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
_INFLIGHT_KEY = f"{DOMAIN}_card_inflight"
_FAILED_KEY = f"{DOMAIN}_card_failed"
_SLOTS_KEY = f"{DOMAIN}_card_slots"

#: Wie viele Abfragen der Karte gleichzeitig zur App laufen. Die App erlaubt vier und
#: antwortet sonst mit 429; ein Platz bleibt frei für die Auswahl im Editor.
MAX_APP_QUERIES = 3
#: Wie viele Abfragen (laufende und wartende) normale Benutzer je Verbindung gleichzeitig offen haben
#: dürfen. Darüber kommt sofort "beschäftigt", sonst könnte ein einzelner Benutzer die Warteschlange
#: füllen und die Karten der Administratoren hinter sich warten lassen. Administratoren sind ausgenommen.
MAX_QUEUED_OTHERS = MAX_APP_QUERIES + 8
#: Eine Abweisung der App (Angaben ungültig, nicht gefunden, zu groß) wird so lange gemerkt, statt die App
#: mit derselben Frage immer wieder zu belasten.
FAILURE_SECONDS = 5.0

# Die Codes sind der Vertrag mit der Karte (sie übersetzt sie selbst).
ERROR_NOT_LOADED = "not_loaded"
ERROR_APP_OUTDATED = "app_outdated"
ERROR_NOT_FOUND = "not_found"
ERROR_BUSY = "busy"
ERROR_AUTH = "auth_failed"
ERROR_UNREACHABLE = "unreachable"
ERROR_INVALID = "invalid"
ERROR_TOO_LARGE = "too_large"
ERROR_APP_ERROR = "app_error"

_DAY = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z"
_PX_STEP = 100
_ENTITY = r"^[a-z0-9_]+\.[a-z0-9_]+\Z"


def _px(msg: dict[str, Any]) -> int:
    """Breite der Karte in Schritten von 100 Bildpunkten, nach oben gerundet: ähnlich breite Karten
    teilen sich eine Antwort, und die App bekommt genau die Breite, nach der der Zwischenspeicher fragt."""
    width = int(msg.get("px", 0))
    return min(CARD_MAX_PX, -(-width // _PX_STEP) * _PX_STEP) if width > 0 else 0


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
    hass.data[_INFLIGHT_KEY] = {}
    hass.data[_FAILED_KEY] = {}
    hass.data[_SLOTS_KEY] = {}
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
    websocket_api.async_register_command(hass, ws_card_table)


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


def _recent_failure(hass: HomeAssistant, key: tuple) -> ZeitarchivCardError | None:
    hit = hass.data[_FAILED_KEY].get(key)
    if hit is None or time.monotonic() - hit[0] > FAILURE_SECONDS:
        return None
    return hit[1]


def _remember_failure(hass: HomeAssistant, key: tuple, err: ZeitarchivCardError) -> None:
    failed = hass.data[_FAILED_KEY]
    now = time.monotonic()
    for old in [k for k, (stamp, _) in failed.items() if now - stamp > FAILURE_SECONDS]:
        del failed[old]
    if len(failed) < CACHE_MAX_ENTRIES:
        failed[key] = (now, err)


async def _query_app(hass: HomeAssistant, entry, key: tuple, call, *, admin: bool) -> dict[str, Any]:
    """Eine Abfrage an die App. Gleiche Abfragen, die gleichzeitig eintreffen (ein Dashboard mit
    mehreren Karten desselben Charts, mehrere Betrachter), teilen sich einen Abruf; verschiedene
    laufen höchstens MAX_APP_QUERIES gleichzeitig, der Rest wartet. So bekommt niemand ein
    "beschäftigt" der App, nur weil ein Dashboard viele Karten auf einmal öffnet. Normale Benutzer
    dürfen dabei höchstens MAX_QUEUED_OTHERS Abfragen offen haben (siehe dort)."""
    inflight: dict[tuple, asyncio.Task] = hass.data[_INFLIGHT_KEY]
    task = inflight.get(key)
    if task is None:
        failure = _recent_failure(hass, key)
        if failure is not None:
            raise failure
        if not admin and sum(1 for other in inflight if other[0] == entry.entry_id) >= MAX_QUEUED_OTHERS:
            raise ZeitarchivCardError("Zu viele offene Abfragen", 429)
        slots = hass.data[_SLOTS_KEY].setdefault(entry.entry_id, asyncio.Semaphore(MAX_APP_QUERIES))
        # Vor dem Warten lesen: wird die Verbindung währenddessen entladen, fehlt runtime_data.
        client = entry.runtime_data.client

        async def run() -> dict[str, Any]:
            try:
                async with slots:
                    result = await hass.async_add_executor_job(call, client)
                _remember(hass, key, result)
                return result
            except ZeitarchivCardError as err:
                # Nur Antworten, die sich nicht von selbst ändern; 429 und 5xx sollen neu versucht werden.
                if err.status in (400, 404, 413) and not err.route_missing:
                    _remember_failure(hass, key, err)
                raise
            finally:
                inflight.pop(key, None)

        # Nicht eifrig starten: der Abruf darf erst laufen, wenn er in inflight eingetragen ist, sonst
        # räumt sein finally einen Eintrag ab, der noch gar nicht da war, und er bliebe für immer stehen.
        task = hass.async_create_task(run(), eager_start=False)
        inflight[key] = task
        # Ein Fehler, den gerade niemand mehr abwartet, ist trotzdem "gesehen".
        task.add_done_callback(lambda done: done.cancelled() or done.exception())
    # shield: bricht ein Betrachter ab (Verbindung zu), läuft der Abruf für die anderen weiter.
    return await asyncio.shield(task)


def shared_ids(entry, option: str) -> set[int]:
    """Die für alle Benutzer freigegebenen IDs (Optionen der Verbindung)."""
    return {value for value in entry.options.get(option, []) if isinstance(value, int)}


def _may_see(hass: HomeAssistant, connection, msg: dict[str, Any], option: str, item_id: int) -> bool:
    """Administratoren dürfen jedes Chart und jede Tabelle, andere nur freigegebene.
    Antwortet selbst mit "unauthorized", wenn nicht. Die Prüfung steht vor dem
    Zwischenspeicher, der Antworten für alle Betrachter gemeinsam hält."""
    if connection.user.is_admin:
        return True
    entry = _entry(hass, msg.get("entry_id"))
    if entry is not None and item_id in shared_ids(entry, option):
        return True
    connection.send_error(msg["id"], "unauthorized", "Nicht für die Karte freigegeben")
    return False


def _mark_shared(entry, result: dict[str, Any]) -> dict[str, Any]:
    """Für Administratoren: je Eintrag, ob ihn auch andere Benutzer sehen (Hinweis im Editor)."""
    charts, tables = shared_ids(entry, CONF_CARD_SHARED_CHARTS), shared_ids(entry, CONF_CARD_SHARED_TABLES)
    return {
        **result,
        "items": [{**item, "shared": item.get("id") in charts} for item in result.get("items") or []],
        "tables": [{**item, "shared": item.get("id") in tables} for item in result.get("tables") or []],
    }


def _only_shared(entry, result: dict[str, Any]) -> dict[str, Any]:
    """Die Auswahl der Karte für Nicht-Administratoren: nur Freigegebenes."""
    charts, tables = shared_ids(entry, CONF_CARD_SHARED_CHARTS), shared_ids(entry, CONF_CARD_SHARED_TABLES)
    return {
        **result,
        "items": [item for item in result.get("items") or [] if item.get("id") in charts],
        "tables": [item for item in result.get("tables") or [] if item.get("id") in tables],
    }


async def _fetch(
    hass: HomeAssistant, connection, msg: dict[str, Any], key: tuple, call, capability: str = "cards",
    transform=None,
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
            result = await _query_app(hass, entry, key, call, admin=connection.user.is_admin)
        except ZeitarchivAuthError:
            connection.send_error(msg["id"], ERROR_AUTH, "Zugangsdaten von der App abgelehnt")
            return
        except ZeitarchivCardError as err:
            if err.route_missing:
                connection.send_error(msg["id"], ERROR_APP_OUTDATED, "Die Zeitarchiv-App ist zu alt für die Karte")
            elif err.status >= 500:
                connection.send_error(msg["id"], ERROR_APP_ERROR, "Die Zeitarchiv-App hat einen Fehler gemeldet")
            elif err.status == 429:
                connection.send_error(msg["id"], ERROR_BUSY, "Zeitarchiv ist gerade beschäftigt")
            elif err.status == 413:
                connection.send_error(msg["id"], ERROR_TOO_LARGE, "Zu viele Datenpunkte für diesen Zeitraum")
            elif err.status == 400:
                connection.send_error(msg["id"], ERROR_INVALID, "Die Angaben der Karte hat die App abgelehnt")
            else:
                connection.send_error(msg["id"], ERROR_NOT_FOUND, "Chart oder Entität nicht gefunden")
            return
        except ValueError as err:
            # Der Client nimmt nur IDs und feste Wörter; was durch das Schema rutscht, ist ungültig, nicht ein Fehler.
            _LOGGER.debug("Karte: Angabe nicht angenommen: %s", err)
            connection.send_error(msg["id"], ERROR_INVALID, "Die Angaben der Karte hat die App abgelehnt")
            return
        except ZeitarchivApiError as err:
            _LOGGER.debug("Karte: Abruf in der App fehlgeschlagen: %s", err)
            connection.send_error(msg["id"], ERROR_UNREACHABLE, "Zeitarchiv nicht erreichbar")
            return
    connection.send_result(msg["id"], transform(entry, result) if transform else result)


@websocket_api.websocket_command(
    {"type": "zeitarchiv/card/items", probatio.Optional("entry_id"): str}
)
@websocket_api.async_response
async def ws_card_items(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Gespeicherte Charts und Tabellen für den Editor der Karte; Nicht-Administratoren
    sehen nur die freigegebenen (und im Editor ohnehin nichts zu tun)."""
    await _fetch(
        hass, connection, msg, ("items",), lambda client: client.get_card_items(),
        transform=_mark_shared if connection.user.is_admin else _only_shared,
    )


@websocket_api.websocket_command(
    {
        "type": "zeitarchiv/card/chart",
        probatio.Required("chart_id"): probatio.All(int, probatio.Range(min=1)),
        probatio.Optional("at"): probatio.All(str, probatio.Match(_DAY)),
        probatio.Optional("px", default=0): probatio.All(int, probatio.Range(min=0, max=CARD_MAX_PX)),
        probatio.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_card_chart(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Einstellungen und Daten eines gespeicherten Charts."""
    chart_id, at, px = msg["chart_id"], msg.get("at"), _px(msg)
    if not _may_see(hass, connection, msg, CONF_CARD_SHARED_CHARTS, chart_id):
        return
    await _fetch(hass, connection, msg, ("chart", chart_id, at, px), lambda client: client.get_card_chart(chart_id, at, px))


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
        probatio.Optional("px", default=0): probatio.All(int, probatio.Range(min=0, max=CARD_MAX_PX)),
        probatio.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_card_series(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Einstellungen und Daten für frei gewählte Entitäten."""
    ids, period, style, at, px = list(msg["entity_ids"]), msg["period"], msg["style"], msg.get("at"), _px(msg)
    await _fetch(
        hass, connection, msg, ("series", tuple(ids), period, style, at, px),
        lambda client: client.get_card_series(ids, period, style, at, px), capability="card_series",
    )


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
    """Kurze Reihe einer Entität für die Sparkline unter einer Kachelkarte (alle Benutzer)."""
    entity_id, range_key = msg["entity_id"], msg["range"]
    await _fetch(
        hass, connection, msg, ("spark", entity_id, range_key),
        lambda client: client.get_card_spark(entity_id, range_key), capability="card_spark",
    )


@websocket_api.websocket_command(
    {
        "type": "zeitarchiv/card/table",
        probatio.Required("table_id"): probatio.All(int, probatio.Range(min=1)),
        probatio.Optional("at"): probatio.All(str, probatio.Match(_DAY)),
        probatio.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_card_table(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Aufbau und fertige Abfrage einer gespeicherten Vergleichstabelle."""
    table_id, at = msg["table_id"], msg.get("at")
    if not _may_see(hass, connection, msg, CONF_CARD_SHARED_TABLES, table_id):
        return
    await _fetch(
        hass, connection, msg, ("table", table_id, at), lambda client: client.get_card_table(table_id, at),
        capability="card_table",
    )
