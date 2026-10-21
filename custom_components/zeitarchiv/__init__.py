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
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_cached_translations
from homeassistant.loader import async_get_integration

from .api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivClient, capabilities_from
from .const import (
    CONF_API_TOKEN,
    CONF_DECIMAL_PLACES,
    DEFAULT_DECIMAL_PLACES,
    DOMAIN,
    SIGNAL_TEXT_STATES,
)
from .coordinator import ZeitarchivNoticesCoordinator
from .data import ZeitarchivConfigEntry, ZeitarchivRuntimeData
from .events import build_event, is_text_state
from .filtering import is_state_already_sent, is_state_value_change
from .queue_writer import ZeitarchivQueueWriter
from .registry_filter import ArchiveFilterMatcher, migrate_legacy_domains
from . import repairs as repairs_mod

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list = ["sensor", "binary_sensor"]

# Persistierter "zuletzt gesendet"-Wasserstand je Entität (entity_id → ts) —
# verhindert, dass der Initial-Snapshot beim Neuladen (Options-Flow-Änderung,
# nicht nur ein HA-Neustart) Werte erneut sendet, die serverseitig längst
# bekannt sind. Ohne den Wasserstand verlässt sich der Snapshot vollständig
# auf die serverseitige Dedup-Prüfung (siehe Kommentar bei initial_events
# unten) — bei genügend Entitäten wird daraus ein Batch aus fast nur
# Duplikaten, der auf der App-Seite pro Duplikat eine Archiv-Datei liest und
# dabei den dortigen Index-Lock so dicht besetzt hält, dass parallele
# Anfragen mit 503 scheitern (an einer echten Installation beobachtet).
_WATERMARK_STORAGE_VERSION = 1


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entfernt den alten Domainfilter bestandserhaltend aus den Optionen."""
    if entry.version > 2:
        return False
    if entry.version < 2:
        migrated = _migrate_legacy_domain_options(hass, dict(entry.options))
        hass.config_entries.async_update_entry(entry, options=migrated, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZeitarchivConfigEntry) -> bool:
    """Richtet Zeitarchiv aus einem Config-Entry ein."""
    integration = await async_get_integration(hass, DOMAIN)
    client = ZeitarchivClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_TOKEN],
        integration_version=str(integration.version) if integration.version else None,
        language=hass.config.language,
    )
    # Verbindungstest vor allem anderen, damit ein Abbruch weder Thread noch
    # Listener zurücklässt. Nur ein abgelehnter Token bricht ab: mit ihm kann
    # ohnehin nichts geschrieben werden, und ConfigEntryAuthFailed startet
    # direkt den Reauth. Eine nicht erreichbare App dagegen bewusst KEIN
    # ConfigEntryNotReady — der Queue-Writer puffert und wiederholt, bis sie
    # wieder da ist; mit ConfigEntryNotReady gingen alle Zustandsänderungen
    # bis zum nächsten Setup-Versuch verloren. Im Demo-Modus ebenfalls kein
    # Abbruch: dort pausiert der Queue-Writer ruhig (siehe repairs.py,
    # demo_mode_paused), statt einen Tokenwechsel zu verlangen.
    # Fähigkeiten der App (siehe api.capabilities_from): "state" heißt, sie
    # nimmt Text-Zustände an. Beim Start aus /api/health, danach jede Minute
    # aus /api/notices nachgeführt (_sync_capabilities unten) — so greift
    # ein App-Update ohne Neustart von Home Assistant. Bis zur ersten
    # Antwort gilt: keine Fähigkeit, also das bisherige Verhalten.
    app_capabilities: dict[str, bool] = {"state": False}
    caps: frozenset[str] = frozenset()
    try:
        caps = await hass.async_add_executor_job(client.test_connection)
        app_capabilities["state"] = "state" in caps
    except ZeitarchivAuthError as err:
        if err.demo_mode is not True:
            raise ConfigEntryAuthFailed(str(err)) from err
    except ZeitarchivApiError as err:
        _LOGGER.info(
            "Zeitarchiv-Ziel %s beim Start nicht erreichbar, Events werden gepuffert: %s",
            entry.title,
            err,
        )
    # KI-Zugriff (ROADMAP 1.31): Die App meldet "ai", sobald sie /api/ai/*
    # kennt. Ob der Zugriff eingeschaltet ist, entscheidet sie selbst (403);
    # die Werkzeuge reichen ihre Antwort dann unverändert an das Modell weiter.
    # Die Fähigkeit wird nur beim Start gelesen: Nach einem App-Update braucht
    # es ein Neuladen der Integration (V1 führt das über /api/notices nach).
    if "ai" in caps:
        _register_ai(hass, entry, client)
    # Wasserstand VOR dem Queue-Writer laden: on_batch_sent unten schreibt
    # bereits ab dem ersten erfolgreichen Batch in dasselbe Dict.
    watermark_store = _watermark_store(hass, entry)
    watermark: dict[str, float] = await watermark_store.async_load() or {}

    async def _persist_watermark(batch: list[dict]) -> None:
        changed = False
        for event in batch:
            entity_id = event.get("entity_id")
            ts = event.get("ts")
            if entity_id is None or ts is None:
                continue
            if ts > watermark.get(entity_id, 0.0):
                watermark[entity_id] = ts
                changed = True
        if changed:
            await watermark_store.async_save(watermark)

    # on_auth_failed läuft im Hintergrund-Thread des Queue-Writers (siehe
    # dessen Docstring, kein homeassistant-Import dort) — hass.add_job statt
    # eines direkten awaits, weil wir hier nicht im Event-Loop sind.
    # async_start_reauth dedupliziert selbst (HA startet keinen zweiten Reauth-
    # Flow, während schon einer offen ist), ein Aufruf pro fehlgeschlagenem
    # Batch ist also unproblematisch. Das ist der Gegenpart zur Möglichkeit,
    # den Token in der Zeitarchiv-GUI selbst neu zu generieren
    # (Einstellungen → Verbindung) — ohne das hier würde ein dort geänderter
    # Token nur endlos leise im Log ausstehende Batches erzeugen.
    # on_demo_mode_detected/on_demo_mode_resolved (DEMO_MODUS_REAUTH_PLAN.md):
    # dieselbe hass.add_job-Notwendigkeit wie on_auth_failed (Hintergrund-
    # Thread, kein Event-Loop) — repairs_mod.async_set_demo_mode_paused_issue
    # ruft ir.async_create_issue/async_delete_issue auf, beide müssen auf dem
    # Event-Loop laufen, nicht auf dem Queue-Writer-Thread. on_batch_sent
    # ebenso: _persist_watermark ist eine Koroutine und muss auf dem
    # Event-Loop laufen, nicht auf dem Queue-Writer-Thread.
    queue_writer = ZeitarchivQueueWriter(
        client,
        on_auth_failed=lambda: hass.add_job(entry.async_start_reauth, hass),
        on_demo_mode_detected=lambda: hass.add_job(
            repairs_mod.async_set_demo_mode_paused_issue, hass, entry, True
        ),
        on_demo_mode_resolved=lambda: hass.add_job(
            repairs_mod.async_set_demo_mode_paused_issue, hass, entry, False
        ),
        on_batch_sent=lambda batch: hass.add_job(_persist_watermark, batch),
    )
    queue_writer.start()
    notices_coordinator = ZeitarchivNoticesCoordinator(hass, entry, client)

    filters = _resolve_filters(hass, entry.options)
    decimal_places = entry.options.get(CONF_DECIMAL_PLACES, DEFAULT_DECIMAL_PLACES)

    # Ausgewählte Entitäten, deren letzter Zustand reiner Text war (siehe
    # events.is_text_state) — Grundlage der Repair-Karte und des Binärsensors
    # "Nicht archivierbare Entitäten". Ohne sie fällt eine solche Entität
    # stillschweigend weg: sie kommt nie in der App an und ist dort deshalb
    # auch nicht auswählbar. Während des Initial-Snapshots wird nur gesammelt
    # und danach einmal aktualisiert, statt je Entität.
    text_state_entities: set[str] = set()
    snapshot_done = False
    # Zuletzt veröffentlichter Stand, nur auf dem Event-Loop geschrieben —
    # der Binärsensor liest ihn beim Anlegen, danach kommt jede Änderung per
    # Dispatcher-Signal.
    text_states_view: dict[str, tuple[str, ...]] = {"entities": ()}

    @callback
    def _async_text_states_changed(entity_ids: tuple[str, ...]) -> None:
        text_states_view["entities"] = entity_ids
        repairs_mod.async_set_text_states_issue(hass, entry, entity_ids)
        async_dispatcher_send(hass, SIGNAL_TEXT_STATES.format(entry.entry_id))

    def _publish_text_states() -> None:
        # hass.add_job statt eines direkten Aufrufs: state_changed-Listener
        # ohne @callback laufen im Executor, Repair-Registry und Dispatcher
        # brauchen den Event-Loop — erst das @callback oben bringt den Job
        # dorthin (eine undekorierte Funktion schickte add_job wiederum in den
        # Executor). Als Tupel übergeben, damit der Job eine stabile Kopie sieht.
        hass.add_job(_async_text_states_changed, tuple(sorted(text_state_entities)))

    def _text_allowed(entity_id: str) -> bool:
        # Nur EINZELN ausgewählte Entitäten: ein Muster wie sensor.* oder
        # eine Auswahl über Bereich/Gerät/Label holt Text-Sensoren nicht mit
        # (ROADMAP 1.29 — sonst kämen Versionsnummern, Geräte-IDs & Co. mit).
        return app_capabilities["state"] and entity_id in filters.included_entities

    def _track_text_state(entity_id: str, is_text: bool) -> None:
        if is_text == (entity_id in text_state_entities):
            return
        if is_text:
            text_state_entities.add(entity_id)
            _LOGGER.warning(
                "Zeitarchiv archiviert %s noch nicht: der Zustand ist Text statt "
                "einer Zahl, und die App (Ziel=%s) kann Text-Zustände noch "
                "nicht annehmen. Nach einem Update der App geschieht das automatisch",
                entity_id,
                entry.title,
            )
        else:
            text_state_entities.discard(entity_id)
        if snapshot_done:
            _publish_text_states()

    def _enqueue_state(state: State) -> bool:
        """Filtert und uebergibt einen aktuellen oder geaenderten Zustand."""
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        if not filters.matches(entity_id):
            return False

        allow_text = _text_allowed(entity_id)
        is_text = is_text_state(domain, state.state)
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
            allow_text=allow_text,
            state_label=_state_label(hass, state) if allow_text and is_text else None,
        )
        if payload is None:
            # Hinweis nur für einzeln ausgewählte Entitäten (dann kann die
            # App sie nur noch nicht annehmen) — über ein Muster getroffene
            # Text-Sensoren sind gewollt außen vor, eine Karte dafür wäre bei
            # breiten Mustern schlicht voll.
            if is_text and entity_id in filters.included_entities:
                _track_text_state(entity_id, True)
            return False
        _track_text_state(entity_id, False)
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
    # doppelt gesendeter identischer Zeitstempel wird von der App dedupliziert —
    # das bleibt das Sicherheitsnetz für den seltenen Rest-Fall (z. B. ein
    # Zustand, der sich exakt waehrend des Ladens aendert), der Regelfall
    # (ein Neuladen ohne echte Aenderungen seit dem letzten erfolgreichen
    # Batch) wird jetzt schon vorher ueber den Wasserstand ausgefiltert.
    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, _handle_state_changed)

    def _already_sent(state: State) -> bool:
        return is_state_already_sent(
            state.last_updated.timestamp() if state.last_updated else None,
            watermark.get(state.entity_id),
        )

    all_states = list(hass.states.async_all())
    already_sent_count = sum(1 for state in all_states if _already_sent(state))
    initial_events = sum(
        _enqueue_state(state) for state in all_states if not _already_sent(state)
    )
    snapshot_done = True
    if text_state_entities:
        _publish_text_states()
    _LOGGER.info(
        "Zeitarchiv-Initialzustand beim Laden vorgemerkt · Ziel=%s · Events=%d · "
        "bereits gesendet (übersprungen)=%d",
        entry.title,
        initial_events,
        already_sent_count,
    )

    entry.runtime_data = ZeitarchivRuntimeData(
        client=client,
        queue_writer=queue_writer,
        remove_listener=remove_listener,
        filters=filters,
        notices_coordinator=notices_coordinator,
        text_states=text_states_view,
    )

    def _sync_repairs() -> None:
        repairs_mod.async_sync_issues(
            hass, entry, (notices_coordinator.data or {}).get("notices", [])
        )

    @callback
    def _sync_capabilities() -> None:
        data = notices_coordinator.data
        if not data or data.get("unauthenticated"):
            return
        had_state = app_capabilities["state"]
        app_capabilities["state"] = "state" in capabilities_from(data)
        if app_capabilities["state"] and not had_state:
            # Die App kann Text-Zustände jetzt annehmen (App-Update): den
            # aktuellen Zustand der bisher abgewiesenen Entitäten gleich
            # nachreichen, statt auf ihre nächste Änderung zu warten.
            for entity_id in sorted(text_state_entities):
                current = hass.states.get(entity_id)
                if current is not None:
                    _enqueue_state(current)

    entry.async_on_unload(notices_coordinator.async_add_listener(_sync_capabilities))

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
    # Erst NACH dem obigen runtime_data weiterreichen — sensor.py liest
    # genau diese Daten in seinem eigenen async_setup_entry.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _register_ai(hass: HomeAssistant, entry: ZeitarchivConfigEntry, client: ZeitarchivClient) -> None:
    """Meldet die LLM-API an, wenn Home Assistant neu genug ist (2026.10).

    Der Import steht hier und nicht oben: ai.py braucht probatio und die neuen
    Tool-Bausteine und lässt sich auf älterem Home Assistant gar nicht laden.
    Statt Kompatibilitätscode für voluptuous gibt es dort einmal einen Hinweis.
    """
    try:
        from . import ai as ai_mod  # noqa: PLC0415
    except (ImportError, AttributeError):
        _LOGGER.warning(
            "Der KI-Zugriff von Zeitarchiv braucht Home Assistant 2026.10 oder neuer "
            "und bleibt bis dahin ausgeschaltet"
        )
        return
    entry.async_on_unload(ai_mod.async_register(hass, entry, client))


async def async_remove_entry(hass: HomeAssistant, entry: ZeitarchivConfigEntry) -> None:
    """Löscht den Wasserstand einer entfernten Verbindung aus .storage —
    sonst bliebe je gelöschtem Entry eine verwaiste Datei zurück."""
    await _watermark_store(hass, entry).async_remove()


def _watermark_store(hass: HomeAssistant, entry: ConfigEntry) -> Store[dict[str, float]]:
    return Store(hass, _WATERMARK_STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_watermark")


async def _async_update_listener(hass: HomeAssistant, entry: ZeitarchivConfigEntry) -> None:
    """Lädt den Entry neu, wenn sich die Options-Flow-Filter ändern."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZeitarchivConfigEntry) -> bool:
    """Räumt Listener, Sensoren und Hintergrund-Thread beim Entfernen/Neuladen auf."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = entry.runtime_data
    data.remove_listener()
    # Sonst blieben Repair-Karten einer entfernten/neu geladenen Verbindung
    # verwaist stehen, bis zufällig dieselbe Meldung erneut aktiv wird.
    repairs_mod.async_clear_issues(hass, entry)
    stopped = await hass.async_add_executor_job(data.queue_writer.stop)
    if not stopped:
        _LOGGER.error("Zeitarchiv-Queue-Worker konnte nicht sauber beendet werden")
        return False
    return True


def _state_label(hass: HomeAssistant, state: State) -> str | None:
    """HA-Übersetzung eines Text-Zustands (z. B. "heat" → "Heizen"), oder
    None, wenn HA keine kennt. Dieselben Schlüssel wie der Template-Filter
    state_translated, aber je eine gezielte Abfrage für genau eine
    Integration statt der dort zusammengeführten Übersetzungen aller
    geladenen Integrationen — das läuft hier bei jeder Zustandsänderung.
    Liest nur den Übersetzungs-Cache, lädt nichts nach."""
    domain = state.domain
    language = hass.config.language
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    if registry_entry is not None and registry_entry.translation_key:
        platform = registry_entry.platform
        translations = async_get_cached_translations(hass, language, "entity", platform)
        key = f"component.{platform}.entity.{domain}.{registry_entry.translation_key}.state.{state.state}"
        if key in translations:
            return translations[key]
    translations = async_get_cached_translations(hass, language, "entity_component", domain)
    device_class = state.attributes.get("device_class")
    for group in ((device_class,) if device_class else ()) + ("_",):
        key = f"component.{domain}.entity_component.{group}.state.{state.state}"
        if key in translations:
            return translations[key]
    return None


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
