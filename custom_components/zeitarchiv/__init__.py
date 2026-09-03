"""Die Zeitarchiv-Integration.

Zwei unabhängige Richtungen:

1. HA → App (Schreibpfad, der eigentliche Zweck): hört auf state_changed,
   filtert nach den Options-Flow-Einstellungen, reicht passende Zustände an
   die Queue/Batch/Retry-Logik weiter, die sie an die App schickt. Erzeugt
   selbst KEINE Entities für die archivierten Daten (die gehören der App,
   nicht HA) — nur eine Handvoll Diagnose-Sensoren (sensor.py,
   entity_category=diagnostic) über den Zustand des Schreibpfads selbst.
   Reines Polling von bereits im Prozess vorhandenem Zustand (kein I/O),
   deshalb dort bewusst kein DataUpdateCoordinator.

2. App → HA (Rückkanal, siehe coordinator.py/binary_sensor.py/repairs.py):
   pollt /api/notices und macht daraus automatisierbare Health-Entities
   sowie Repairs für kritische Fälle. Hier holt ein DataUpdateCoordinator
   tatsächlich externe Daten (das Haus-Muster von fritzbox_phone/oscam) —
   ein Fehlschlag blockiert absichtlich nicht den Schreibpfad, siehe
   coordinator.py.
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
from homeassistant.loader import async_get_integration

from .api import ZeitarchivClient
from .const import (
    CONF_API_TOKEN,
    CONF_DECIMAL_PLACES,
    DEFAULT_DECIMAL_PLACES,
    DOMAIN,
)
from .coordinator import ZeitarchivNoticesCoordinator
from .events import build_event
from .filtering import is_state_value_change
from .queue_writer import ZeitarchivQueueWriter
from .registry_filter import ArchiveFilterMatcher, migrate_legacy_domains
from . import repairs as repairs_mod

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list = ["sensor", "binary_sensor"]


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
    integration = await async_get_integration(hass, DOMAIN)
    client = ZeitarchivClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_TOKEN],
        integration_version=str(integration.version) if integration.version else None,
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
    notices_coordinator = ZeitarchivNoticesCoordinator(hass, entry, client)

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
        "notices_coordinator": notices_coordinator,
    }

    def _sync_repairs() -> None:
        repairs_mod.async_sync_issues(hass, entry, notices_coordinator.data or [])

    entry.async_on_unload(notices_coordinator.async_add_listener(_sync_repairs))
    # Erster Abruf bewusst mit async_refresh() statt
    # async_config_entry_first_refresh(): Letzteres würde bei Fehlschlag
    # (App unerreichbar, oder zu alte App-Version ohne /api/notices)
    # ConfigEntryNotReady auslösen und damit die GESAMTE Integration inkl.
    # Schreibpfad blockieren — für dieses optionale Zusatzfeature
    # unangemessen (siehe coordinator.py).
    await notices_coordinator.async_refresh()
    _sync_repairs()

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
    # Sonst blieben Repair-Karten einer entfernten/neu geladenen Verbindung
    # verwaist stehen, bis zufällig dieselbe Meldung erneut aktiv wird.
    repairs_mod.async_clear_issues(hass, entry)
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
