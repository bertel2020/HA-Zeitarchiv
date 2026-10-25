"""Label-, Bereichs- und Geräte-Ereignisse aus den Registries (ROADMAP 1.33, Phase 2).

Dünne Schicht um registry_events.py: hört auf die vier Registry-Ereignisse,
bündelt einen Burst (``FLUSH_DELAY`` Sekunden) und dann

- sendet den aktuellen Zustand der Entitäten nach, die dadurch NEU erfasst
  sind (z. B. Label in HA gesetzt) — über ``resend_state`` mit
  Wasserstand-Schutz, sonst erschienen ruhige Sensoren erst bei der nächsten
  Änderung;
- vermerkt im Verlauf, wenn das Zeitarchiv-Label in HA von Assistenten-
  Entitäten genommen wurde (``manual_ha``, ein Eintrag je Burst);
- stößt den Katalog an (gedrosselt wie ``CatalogSender``).

Kein Reload, kein Eingriff in Queue oder Wasserstand; Fehler werden geloggt,
nie geworfen. Die Listener meldet ``async_stop`` ab (``entry.async_on_unload``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HassJob, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN
from .registry_events import EVENTS, classify_registry_event, newly_selected
from .registry_filter import ArchiveFilterMatcher
from .selection_ledger import assistant_label_removed

if TYPE_CHECKING:
    from .catalog_sync import CatalogSender
    from .selection_sync import SelectionManager

_LOGGER = logging.getLogger(__name__)

#: Registry-Bursts (z. B. ein Label an 30 Entitäten) werden so lange gesammelt.
FLUSH_DELAY = 5.0


class RegistryWatcher:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        filters: ArchiveFilterMatcher,
        resend_state: Callable[[State], bool],
        catalog_sender: CatalogSender | None,
        selection: SelectionManager | None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._filters = filters
        self._resend_state = resend_state
        self._catalog = catalog_sender
        self._selection = selection
        self._entities = er.async_get(hass)
        self._selected: set[str] = set()
        self._touched: set[str] = set()
        self._wide = False
        self._drift: set[str] = set()
        self._unsubs: list[Callable[[], None]] = []
        self._cancel_timer: Callable[[], None] | None = None
        self._stopped = False

    @callback
    def async_start(self) -> None:
        """Ausgangsmenge merken und die Listener anmelden. Wirft nie."""
        try:
            self._selected = self._selected_now()
            for event_type in EVENTS:
                self._unsubs.append(self._hass.bus.async_listen(event_type, self._handle_event))
        except Exception:  # noqa: BLE001 — ein Zusatz, darf das Setup nicht stören
            _LOGGER.warning("Registry-Ereignisse für Zeitarchiv nicht abonniert", exc_info=True)

    @callback
    def async_stop(self) -> None:
        self._stopped = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    def _selected_now(self) -> set[str]:
        return {state.entity_id for state in self._hass.states.async_all() if self._filters.matches(state.entity_id)}

    def _managed_label_id(self) -> str | None:
        return self._selection.ledger.get("label_id") if self._selection is not None else None

    @callback
    def _handle_event(self, event: Event[Any]) -> None:
        try:
            change = classify_registry_event(
                event.event_type, event.data,
                selected_labels=self._filters.selected_labels,
                managed_label_id=self._managed_label_id(),
            )
            if change is None or self._stopped:
                return
            if change.wide:
                self._wide = True
            if change.entity_id:
                self._touched.add(change.entity_id)
                old_entity_id = event.data.get("old_entity_id")
                if isinstance(old_entity_id, str):
                    self._touched.add(old_entity_id)
            if change.device_id:
                self._touched.update(
                    item.entity_id for item in er.async_entries_for_device(
                        self._entities, change.device_id, include_disabled_entities=True
                    )
                )
            if change.old_labels is not None and change.entity_id and self._selection is not None:
                current = self._entities.async_get(change.entity_id)
                if assistant_label_removed(
                    change.entity_id, change.old_labels,
                    current.labels if current is not None else (),
                    self._selection.ledger, self._filters.selected_labels,
                ):
                    self._drift.add(change.entity_id)
            if self._cancel_timer is None:
                # cancel_on_shutdown: Der Timer ist nur eine Bündelung und soll beim Beenden von
                # Home Assistant (oder nach einem fehlgeschlagenen Entladen) nicht als hängend gelten.
                self._cancel_timer = async_call_later(
                    self._hass, FLUSH_DELAY, HassJob(self._fire, "zeitarchiv registry flush", cancel_on_shutdown=True)
                )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Registry-Ereignis nicht ausgewertet", exc_info=True)

    @callback
    def _fire(self, _now: Any) -> None:
        self._cancel_timer = None
        if self._stopped:
            return
        self._entry.async_create_background_task(
            self._hass, self._async_flush(), f"{DOMAIN}_registry_{self._entry.entry_id}"
        )

    async def _async_flush(self) -> None:
        touched, wide, drift = self._touched, self._wide, self._drift
        self._touched, self._wide, self._drift = set(), False, set()
        try:
            after = self._selected_now()
            added = newly_selected(self._selected, after, None if wide else touched)
            self._selected = after
            resent = 0
            for entity_id in added:
                state = self._hass.states.get(entity_id)
                if state is not None and self._resend_state(state):
                    resent += 1
            if added:
                _LOGGER.debug(
                    "Registry-Änderung: neu erfasst=%d · Zustand nachgesendet=%d · Ziel=%s",
                    len(added), resent, self._entry.title,
                )
            if drift and self._selection is not None:
                await self._selection.async_record_label_drift(drift)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Registry-Änderung konnte nicht ausgewertet werden", exc_info=True)
        if self._catalog is not None:
            await self._catalog.async_handle_registry_change()
