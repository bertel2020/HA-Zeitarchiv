"""Auswahl-Assistent, Home-Assistant-Seite (ROADMAP 1.33, Phase 1 und 2).

Dünne Schicht um die reinen Module selection_ledger.py/selection_apply.py:
Ledger-``Store``, echte Registries als ``SelectionPorts``, Abholen der
Aufträge bei geändertem ``selection_rev`` (und einmal nach dem Start),
Anwenden in der Reihenfolge des Vertrags:

    Registry (Labels) → Ledger/Snapshot/Verlauf speichern → Ack an die App
    → zuletzt ``async_update_entry`` (der Reload bricht Hintergrundaufgaben ab)

Alles hier ist ein Zusatz: Fehler werden geloggt, nie geworfen, und berühren
weder Queue noch Wasserstand.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .api import ZeitarchivApiError, ZeitarchivClient, capabilities_from
from .catalog import CATALOG_DOMAINS
from .const import CONF_CARD_SHARED_CHARTS, CONF_CARD_SHARED_TABLES, DOMAIN
from .events import is_text_state
from .registry_filter import ArchiveFilterMatcher
from .selection_apply import apply_jobs, pattern_targets, pending_acks
from .selection_ledger import (
    LABEL_NAME,
    append_log,
    detect_manual_change,
    diff_options,
    empty_ledger,
    make_label_drift_entry,
    normalize_ledger,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1
_UNSET = object()


def selection_store(hass: HomeAssistant, entry: ConfigEntry) -> Store[dict[str, Any]]:
    return Store(hass, _STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_selection")


class HaSelectionPorts:
    """``SelectionPorts`` auf den echten Registries (nur auf dem Event-Loop nutzen)."""

    def __init__(self, hass: HomeAssistant) -> None:
        from homeassistant.helpers import label_registry as lr  # noqa: PLC0415

        self._hass = hass
        self._entities = er.async_get(hass)
        self._devices = dr.async_get(hass)
        self._areas = ar.async_get(hass)
        self._labels = lr.async_get(hass)

    def known(self, entity_id: str) -> bool:
        return self._entities.async_get(entity_id) is not None or self._hass.states.get(entity_id) is not None

    def has_registry_entry(self, entity_id: str) -> bool:
        return self._entities.async_get(entity_id) is not None

    def is_text(self, entity_id: str) -> bool:
        state = self._hass.states.get(entity_id)
        return state is not None and is_text_state(state.domain, state.state)

    def entity_labels(self, entity_id: str) -> set[str]:
        entry = self._entities.async_get(entity_id)
        return set(entry.labels) if entry is not None else set()

    def set_entity_labels(self, entity_id: str, labels: set[str]) -> None:
        self._entities.async_update_entity(entity_id, labels=set(labels))

    def ensure_label(self, known_label_id: str | None) -> str:
        # Über die gespeicherte ID: ein Umbenennen durch den Nutzer bleibt gültig.
        if known_label_id and self._labels.async_get_label(known_label_id) is not None:
            return known_label_id
        existing = self._labels.async_get_label_by_name(LABEL_NAME)
        if existing is not None:
            return existing.label_id
        return self._labels.async_create(LABEL_NAME, icon="mdi:archive-clock-outline").label_id

    def is_selected(self, entity_id: str, options: Mapping[str, Any]) -> bool:
        return ArchiveFilterMatcher(options, self._entities, self._devices, self._areas).matches(entity_id)

    def pattern_targets(
        self, patterns: list[str], before: Mapping[str, Any], after: Mapping[str, Any]
    ) -> list[str]:
        """Entitäten, die neue Muster jetzt erst erfassen (Zustand nachsenden)."""
        if not patterns:
            return []
        old = ArchiveFilterMatcher(before, self._entities, self._devices, self._areas)
        return pattern_targets(
            (state.entity_id for state in self._hass.states.async_all()), patterns, after,
            is_text=self.is_text, was_selected=old.matches,
        )

    def effective(self, options: Mapping[str, Any]) -> set[str]:
        matcher = ArchiveFilterMatcher(options, self._entities, self._devices, self._areas)
        return {
            state.entity_id for state in self._hass.states.async_all()
            if state.domain in CATALOG_DOMAINS and matcher.matches(state.entity_id)
        }


_CARD_KEYS = (CONF_CARD_SHARED_CHARTS, CONF_CARD_SHARED_TABLES)


class SelectionManager:
    """Ledger, Verlauf und Auftrags-Abholung einer Zeitarchiv-Verbindung."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ZeitarchivClient,
        enqueue_state: Callable[[State], bool],
    ) -> None:
        # enqueue_state: Nachsende-Weg mit Wasserstand-Schutz (__init__.py, _resend_state).
        self._hass = hass
        self._entry = entry
        self._client = client
        self._enqueue_state = enqueue_state
        self._store = selection_store(hass, entry)
        self.ledger: dict[str, Any] = empty_ledger()
        self._loaded = False
        self._busy = False
        self._last_rev: Any = _UNSET
        #: Wird nach einer angewendeten Änderung ohne Reload aufgerufen (Katalog sofort senden).
        self.on_changed: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Ledger laden und Options-Änderungen aus HA erkennen (``manual_ha``). Wirft nie."""
        try:
            self.ledger = normalize_ledger(await self._store.async_load())
            options = self._entry.options
            snapshot = self.ledger.get("options_snapshot")
            before = after = None
            if snapshot is not None and diff_options(snapshot, options) is not None:
                ports = HaSelectionPorts(self._hass)
                before, after = ports.effective(snapshot), ports.effective(options)
            had_snapshot = snapshot is not None
            entry = detect_manual_change(
                self.ledger, options, time.time(), effective_before=before, effective_after=after
            )
            if entry is not None or not had_snapshot:
                await self._store.async_save(self.ledger)
            if entry is not None:
                _LOGGER.debug("Auswahl in Home Assistant geändert: %s", entry["ha_detail"].get("summary"))
        except Exception:  # noqa: BLE001 — der Assistent darf das Setup nie stören
            _LOGGER.warning("Auswahl-Verlauf von Zeitarchiv konnte nicht geladen werden", exc_info=True)
        self._loaded = True

    @callback
    def handle_notices(self, data: Mapping[str, Any] | None) -> None:
        """Koordinator-Listener: holt Aufträge nur bei geändertem ``selection_rev``."""
        try:
            if not self._loaded or self._busy or not data or data.get("unauthenticated"):
                return
            if "selection" not in capabilities_from(data):
                return
            rev = data.get("selection_rev")
            if rev == self._last_rev and not self.ledger.get("pending_acks"):
                return
            self._busy = True
            self._entry.async_create_background_task(
                self._hass, self._async_run(rev), f"{DOMAIN}_selection_{self._entry.entry_id}"
            )
        except Exception:  # noqa: BLE001
            self._busy = False
            _LOGGER.warning("Auswahl-Aufträge konnten nicht angestoßen werden", exc_info=True)

    async def _async_run(self, rev: Any) -> None:
        try:
            await self._async_flush_acks()
            raw_jobs = await self._hass.async_add_executor_job(self._client.get_selection_jobs)
            if not raw_jobs:
                self._last_rev = rev
                return
            ports = HaSelectionPorts(self._hass)
            outcome = apply_jobs(
                raw_jobs, self._entry.options, self.ledger, ports, time.time(),
                on_error=lambda entity_id, err: _LOGGER.warning(
                    "Auswahl-Auftrag: %s konnte nicht geändert werden: %s", entity_id, err
                ),
            )
            self._last_rev = rev
            if not outcome.acks:
                return
            await self._store.async_save(self.ledger)
            targets = [*outcome.label_targets, *outcome.include_targets]
            try:
                targets.extend(ports.pattern_targets(outcome.added_patterns, self._entry.options, outcome.options))
            except Exception:  # noqa: BLE001 — nur das Nachsenden fällt weg
                _LOGGER.debug("Treffer neuer Muster nicht ermittelt", exc_info=True)
            self._resend_states(list(dict.fromkeys(targets)))
            await self._async_flush_acks()
            _LOGGER.debug(
                "Auswahl-Aufträge angewendet · Ziel=%s · Aufträge=%d · Optionen geändert=%s",
                self._entry.title, len(outcome.acks), outcome.options_changed,
            )
            if outcome.options_changed:
                # Zuletzt: löst den Reload aus; der neue Setup-Lauf sendet den Katalog.
                # Die Freigabe der Karte gehört nicht zur Auswahl und gilt in ihrem aktuellen Stand:
                # ein Administrator kann sie während der Awaits oben geändert haben, die Kopie vom Anfang
                # wäre veraltet und würde seine Änderung zurückdrehen.
                options = {k: v for k, v in outcome.options.items() if k not in _CARD_KEYS}
                options.update({k: v for k, v in self._entry.options.items() if k in _CARD_KEYS})
                self._hass.config_entries.async_update_entry(self._entry, options=options)
            elif self.on_changed is not None:
                self.on_changed()
        except ZeitarchivApiError as err:
            _LOGGER.debug("Auswahl-Aufträge nicht abrufbar: %s", err)
        except Exception:  # noqa: BLE001 — der Assistent darf nichts anderes stören
            _LOGGER.warning("Auswahl-Aufträge konnten nicht angewendet werden", exc_info=True)
        finally:
            self._busy = False

    async def _async_flush_acks(self) -> None:
        """Offene Acks senden; angenommene (oder der App unbekannte) fallen weg."""
        pending = pending_acks(self.ledger)
        if not pending:
            return
        done = []
        for ack in pending:
            try:
                await self._hass.async_add_executor_job(
                    self._client.ack_selection_job, ack["job_id"], ack["status"], ack["results"], ack.get("message")
                )
            except ZeitarchivApiError as err:
                _LOGGER.debug("Auftrag %s nicht quittiert, neuer Versuch später: %s", ack["job_id"], err)
                break
            # ok:false heißt unbekannt/abgelaufen: nichts mehr zu quittieren.
            done.append(ack["job_id"])
        if done:
            for job_id in done:
                self.ledger["pending_acks"].pop(job_id, None)
            await self._store.async_save(self.ledger)

    async def async_record_label_drift(self, entity_ids: set[str]) -> None:
        """Das Zeitarchiv-Label wurde in HA von Assistenten-Entitäten genommen
        (registry_watch.py): ein ``manual_ha``-Eintrag. Die Ledger-Einträge
        bleiben; die Entitäten erscheinen im Katalog als ``drifted``. Wirft nie."""
        try:
            if not self._loaded or not entity_ids:
                return
            append_log(self.ledger, make_label_drift_entry(entity_ids, time.time()))
            await self._store.async_save(self.ledger)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Label-Änderung nicht im Auswahl-Verlauf vermerkt", exc_info=True)

    def _resend_states(self, entity_ids: list[str]) -> None:
        """Zustand frisch gelabelter, wieder aufgenommener oder per neuem Muster
        erfasster Entitäten sofort einreihen, sonst erschienen ruhige Sensoren
        erst bei ihrer nächsten Änderung. Greift der Filter noch nicht (Label
        oder Muster erst nach dem Reload in den Optionen), übernimmt das der
        Initial-Snapshot des Neuladens."""
        for entity_id in entity_ids:
            try:
                state = self._hass.states.get(entity_id)
                if state is not None:
                    self._enqueue_state(state)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Zustand von %s nicht nachgesendet", entity_id, exc_info=True)


async def async_remove_store(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await selection_store(hass, entry).async_remove()
