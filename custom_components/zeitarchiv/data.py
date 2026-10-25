"""Laufzeitdaten eines Zeitarchiv-Config-Entries (entry.runtime_data).

Eigenes Modul statt in __init__.py, damit sensor.py, binary_sensor.py,
diagnostics.py und repairs.py den Typ importieren können, ohne
__init__.py (und damit den gesamten Schreibpfad) zu importieren.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import State

from .api import ZeitarchivClient
from .coordinator import ZeitarchivNoticesCoordinator
from .queue_writer import ZeitarchivQueueWriter
from .registry_filter import ArchiveFilterMatcher


@dataclass
class ZeitarchivRuntimeData:
    client: ZeitarchivClient
    queue_writer: ZeitarchivQueueWriter
    remove_listener: Callable[[], None]
    # Für diagnostics.py — derselbe Live-Matcher verhindert abweichende
    # Auswertungen zwischen Schreibpfad und Diagnose-Download.
    filters: ArchiveFilterMatcher
    notices_coordinator: ZeitarchivNoticesCoordinator
    # Zuletzt veröffentlichte Liste der Entitäten mit Textwerten — der
    # Binärsensor liest sie beim Anlegen, danach kommt jede Änderung per
    # Dispatcher-Signal (siehe __init__.py).
    text_states: dict[str, tuple[str, ...]]
    # Von repairs.async_sync_issues() nachgeführt, um nicht mehr zutreffende
    # Repair-Issues wieder zu entfernen.
    active_repair_issues: set[str] = field(default_factory=set)
    # Filtert und reiht einen Zustand ein (derselbe Weg wie state_changed) —
    # der Auswahl-Assistent sendet damit nach dem Label-Setzen den aktuellen
    # Zustand nach (selection_sync.py).
    enqueue_state: Callable[[State], bool] | None = None


type ZeitarchivConfigEntry = ConfigEntry[ZeitarchivRuntimeData]
