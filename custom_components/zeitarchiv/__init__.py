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
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import ZeitarchivClient
from .const import (
    CONF_API_TOKEN,
    CONF_DECIMAL_PLACES,
    DEFAULT_DECIMAL_PLACES,
    DOMAIN,
)
from .events import build_event
from .filtering import is_state_value_change
from .queue_writer import ZeitarchivQueueWriter
from .registry_filter import ArchiveFilterMatcher, migrate_legacy_domains

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list = ["sensor"]  # nur Diagnose-Sensoren, siehe sensor.py.


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entfernt den alten Domainfilter bestandserhaltend aus den Optionen."""
    if entry.version > 2:
        return False
    if entry.version < 2:
        migrated = _migrate_legacy_domain_options(hass, dict(entry.options))
        hass.config_entries.async_update_entry(entry, options=migrated, version=2)
    return True


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

    filters = _resolve_filters(hass, entry.options)
    decimal_places = entry.options.get(CONF_DECIMAL_PLACES, DEFAULT_DECIMAL_PLACES)

    def _enqueue_state(state: State) -> bool:
        """Filtert und uebergibt einen aktuellen oder geaenderten Zustand."""
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        if not filters.matches(entity_id):
            return False

        payload = build_event(
            entity_id=entity_id,
            domain=domain,
            state=state.state,
            state_class=state.attributes.get("state_class"),
            unit=state.attributes.get("unit_of_measurement"),
            timestamp=state.last_updated.timestamp()
            if state.last_updated
            else time.time(),
            friendly_name=state.attributes.get("friendly_name"),
            decimal_places=decimal_places,
        )
        if payload is None:
            return False
        queue_writer.enqueue(payload)
        return True

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
        _enqueue_state(new_state)

    # Listener bewusst VOR dem Snapshot registrieren: Aendert sich ein Zustand
    # waehrend des Durchlaufs, geht das Live-Event nicht verloren. Ein eventuell
    # doppelt gesendeter identischer Zeitstempel wird von der App dedupliziert.
    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, _handle_state_changed)

    initial_events = sum(_enqueue_state(state) for state in hass.states.async_all())
    _LOGGER.info(
        "Zeitarchiv-Initialzustand beim Laden vorgemerkt · Ziel=%s · Events=%d",
        entry.title,
        initial_events,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "queue_writer": queue_writer,
        "remove_listener": remove_listener,
        # Für diagnostics.py — derselbe Live-Matcher verhindert abweichende
        # Auswertungen zwischen Schreibpfad und Diagnose-Download.
        "filters": filters,
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


def _resolve_filters(hass: HomeAssistant, options: dict) -> ArchiveFilterMatcher:
    """Erstellt einen Matcher auf den live aktualisierten HA-Registries."""
    return ArchiveFilterMatcher(
        options,
        er.async_get(hass),
        dr.async_get(hass),
        ar.async_get(hass),
    )


def _known_entity_ids(hass: HomeAssistant) -> set[str]:
    """Liefert Registry- und State-IDs für die Domain-Altlastmigration."""
    registry = er.async_get(hass)
    return {state.entity_id for state in hass.states.async_all()} | {
        entry.entity_id for entry in registry.entities.values()
    }


def _migrate_legacy_domain_options(
    hass: HomeAssistant, options: dict[str, object]
) -> dict[str, object]:
    """Entfernt den früheren Domainfilter mit bestandserhaltender Auflösung."""
    return migrate_legacy_domains(options, _known_entity_ids(hass))
