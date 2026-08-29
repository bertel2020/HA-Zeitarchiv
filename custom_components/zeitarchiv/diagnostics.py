"""Diagnose-Unterstützung für Zeitarchiv.

Zeitarchiv erzeugt bewusst keine Entities (siehe __init__.py-Docstring) — der
Diagnose-Download (Einstellungen → Geräte & Dienste → Zeitarchiv → Diagnose
herunterladen) ist deshalb der naheliegende, HA-idiomatische Weg zu prüfen,
ob die Verbindung sauber funktioniert, ohne dafür künstliche Sensor-Entities
einzuführen.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .api import ZeitarchivApiError, ZeitarchivClient
from .const import CONF_API_TOKEN, DOMAIN
from .registry_filter import ArchiveFilterMatcher

TO_REDACT = {CONF_API_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    client: ZeitarchivClient = data["client"]
    queue_writer = data["queue_writer"]

    # Live-Verbindungstest statt nur die Zähler unten zu zeigen — genau die
    # Frage "funktioniert es JETZT" lässt sich aus reinen Zählwerten allein
    # nicht sicher beantworten (die könnten noch vom letzten erfolgreichen
    # Batch vor einer Stunde stammen, während der Token seither abgelaufen ist).
    reachable = True
    connect_error: str | None = None
    try:
        await hass.async_add_executor_job(client.test_connection)
    except ZeitarchivApiError as err:
        reachable = False
        connect_error = str(err)

    filters: ArchiveFilterMatcher = data["filters"]
    matching_now = sum(
        1 for state in hass.states.async_all() if filters.matches(state.entity_id)
    )

    now = time.time()
    last_success_ts = queue_writer.last_success_ts

    return {
        "connection": {
            "reachable_now": reachable,
            "error": connect_error,
            "host": entry.data.get(CONF_HOST),
            "port": entry.data.get(CONF_PORT),
        },
        "queue": {
            "queue_size": queue_writer.queue_size,
            "sent_count_since_start": queue_writer.sent_count,
            "dropped_count_since_start": queue_writer.dropped_count,
            "last_success_seconds_ago": (
                None if last_success_ts is None else round(now - last_success_ts, 1)
            ),
            "last_error": queue_writer.last_error,
        },
        "filters": {
            "matching_entities_now": matching_now,
            "selected_labels": sorted(filters.selected_labels),
            "selected_areas_count": len(filters.selected_areas),
            "selected_devices_count": len(filters.selected_devices),
            "included_entities_count": len(filters.included_entities),
            "excluded_entities_count": len(filters.excluded_entities),
            "included_patterns": filters.included_patterns,
            "excluded_patterns": filters.excluded_patterns,
        },
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
    }
