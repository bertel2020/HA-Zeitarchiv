"""Die Zeitarchiv-Integration.

Reiner Datensenke-Aufbau: hört auf state_changed, filtert nach den
Options-Flow-Einstellungen, reicht passende Zustände an die
Queue/Batch/Retry-Logik weiter, die sie an die App schickt.

Erzeugt selbst KEINE Entities für die archivierten Daten (die gehören der
App, nicht HA) — nur eine Handvoll Diagnose-Sensoren (sensor.py,
entity_category=diagnostic) über den Zustand des Schreibpfads selbst
(Warteschlange, letzte erfolgreiche Übertragung, verworfene Events), damit
sich "funktioniert die Integration gerade" auch ohne Diagnose-Download auf
der Geräteseite ablesen lässt. Deshalb weiterhin kein DataUpdateCoordinator
(das Haus-Muster von fritzbox_phone/oscam) — der ist für Entities gedacht,
die extern abgefragte Daten *anzeigen*; hier reicht simples Polling des
ohnehin schon im Prozess laufenden ZeitarchivQueueWriter-Zustands.
"""

from __future__ import annotations

import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_STATE_CHANGED
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import ZeitarchivClient
from .const import (
    CONF_API_TOKEN,
    CONF_AREAS,
    CONF_DEVICES,
    CONF_DOMAINS,
    CONF_ENTITIES,
    CONF_EXCLUDE_ENTITIES,
    DOMAIN,
)
from .events import build_event
from .filtering import is_state_value_change, should_archive
from .queue_writer import ZeitarchivQueueWriter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list = ["sensor"]  # nur Diagnose-Sensoren, siehe sensor.py.


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Richtet Zeitarchiv aus einem Config-Entry ein."""
    client = ZeitarchivClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_API_TOKEN]
    )
    # on_auth_failed läuft im Hintergrund-Thread des Queue-Writers (siehe
    # dessen Docstring, kein homeassistant-Import dort) — hass.add_job statt
    # eines direkten awaits, weil wir hier nicht im Event-Loop sind.
    # async_start_reauth dedupliziert selbst (HA startet keinen zweiten Reauth-
    # Flow, während schon einer offen ist), ein Aufruf pro fehlgeschlagenem
    # Batch ist also unproblematisch. Das ist der Gegenpart zur Möglichkeit,
    # den Token in der Zeitarchiv-GUI selbst neu zu generieren
    # (Einstellungen → Verbindung) — ohne das hier würde ein dort geänderter
    # Token nur endlos leise im Log ausstehende Batches erzeugen.
    queue_writer = ZeitarchivQueueWriter(
        client, on_auth_failed=lambda: hass.add_job(entry.async_start_reauth, hass)
    )
    queue_writer.start()

    included_entities, included_domains, excluded_entities = _resolve_filters(
        hass, entry.options
    )

    def _handle_state_changed(event: Event[EventStateChangedData]) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return

        # Home Assistant feuert state_changed auch bei reinen Attribut-
        # Änderungen. Solange der eigentliche Zustand identisch ist, wäre ein
        # weiterer Archivpunkt nur ein künstliches Duplikat mit neuer
        # last_updated-Zeit und würde Rohdaten/Queue unnötig aufblasen.
        old_state: State | None = event.data.get("old_state")
        if not is_state_value_change(
            old_state.state if old_state is not None else None, new_state.state
        ):
            return

        entity_id = new_state.entity_id
        domain = entity_id.split(".", 1)[0]
        if not should_archive(
            entity_id, domain, included_entities, included_domains, excluded_entities
        ):
            return

        payload = build_event(
            entity_id=entity_id,
            domain=domain,
            state=new_state.state,
            state_class=new_state.attributes.get("state_class"),
            unit=new_state.attributes.get("unit_of_measurement"),
            timestamp=new_state.last_updated.timestamp() if new_state.last_updated else time.time(),
            friendly_name=new_state.attributes.get("friendly_name"),
        )
        if payload is not None:
            queue_writer.enqueue(payload)

    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, _handle_state_changed)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "queue_writer": queue_writer,
        "remove_listener": remove_listener,
        # Für diagnostics.py — wie viele/welche Entitäten die aktuell
        # aufgelösten Filter tatsächlich erfassen, ohne sie dort erneut
        # auflösen zu müssen.
        "included_entities": included_entities,
        "included_domains": included_domains,
        "excluded_entities": excluded_entities,
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # Erst NACH dem obigen hass.data-Eintrag weiterreichen — sensor.py liest
    # genau diesen Eintrag in seinem eigenen async_setup_entry.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Lädt den Entry neu, wenn sich die Options-Flow-Filter ändern."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Räumt Listener, Sensoren und Hintergrund-Thread beim Entfernen/Neuladen auf."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = hass.data[DOMAIN][entry.entry_id]
    data["remove_listener"]()
    stopped = await hass.async_add_executor_job(data["queue_writer"].stop)
    if not stopped:
        _LOGGER.error("Zeitarchiv-Queue-Worker konnte nicht sauber beendet werden")
        return False
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


def _resolve_filters(
    hass: HomeAssistant, options: dict
) -> tuple[set[str], set[str], set[str]]:
    """Löst Bereiche/Geräte aus den Options einmalig zu konkreten Entity-IDs auf.

    Bekannte Phase-1-Grenze: Entitäten, die *nach* diesem Auflösen neu zu einem
    gewählten Bereich/Gerät hinzukommen, greifen erst nach einem erneuten
    Speichern der Optionen (das löst _async_update_listener und damit einen
    Reload aus) — kein automatisches Nachziehen währenddessen.
    """
    included_domains = set(options.get(CONF_DOMAINS, []))
    excluded_entities = set(options.get(CONF_EXCLUDE_ENTITIES, []))
    included_entities = set(options.get(CONF_ENTITIES, []))

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    selected_areas = set(options.get(CONF_AREAS, []))
    selected_devices = set(options.get(CONF_DEVICES, []))

    if selected_areas or selected_devices:
        for entry in entity_registry.entities.values():
            device = (
                device_registry.async_get(entry.device_id) if entry.device_id else None
            )
            effective_area = entry.area_id or (device.area_id if device else None)
            if effective_area in selected_areas or entry.device_id in selected_devices:
                included_entities.add(entry.entity_id)

    return included_entities, included_domains, excluded_entities
