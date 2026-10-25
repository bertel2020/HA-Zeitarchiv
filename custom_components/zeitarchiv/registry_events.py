"""Registry-Ereignisse für den Auswahl-Assistenten (ROADMAP 1.33, Phase 2).

Ohne Home-Assistant-Import testbar. Entscheidet, welche Registry-Ereignisse
für die Auswahl zählen (Labels, Bereich, Gerätezuordnung), welche Entitäten sie
berühren und welche Entitäten dadurch NEU erfasst sind (deren aktuellen
Zustand sendet registry_watch.py nach). Die HA-Seite bündelt die Ereignisse
und ruft diese Funktionen nur auf.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

EVENT_ENTITY = "entity_registry_updated"
EVENT_DEVICE = "device_registry_updated"
EVENT_AREA = "area_registry_updated"
EVENT_LABEL = "label_registry_updated"
EVENTS = (EVENT_ENTITY, EVENT_DEVICE, EVENT_AREA, EVENT_LABEL)

#: Diese Felder einer Entität bestimmen die Registry-Auswahl.
_ENTITY_FIELDS = frozenset({"labels", "area_id", "device_id"})
#: Und diese eines Geräts.
_DEVICE_FIELDS = frozenset({"labels", "area_id"})


@dataclass(frozen=True)
class RegistryChange:
    """Ein für die Auswahl relevantes Ereignis.

    ``entity_id``/``device_id``: berührte Entität bzw. Gerät (dessen
    Entitäten); ``wide``: berührt potenziell alles (Bereich, Label).
    ``old_labels``: die Labels der Entität vor der Änderung, falls sich ihre
    Labels geändert haben (für die Erkennung „Assistenten-Label entfernt“)."""

    entity_id: str | None = None
    device_id: str | None = None
    wide: bool = False
    old_labels: frozenset[str] | None = None


def _changes(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    changes = data.get("changes")
    return changes if isinstance(changes, Mapping) else None


def classify_registry_event(
    event_type: str,
    data: Mapping[str, Any] | None,
    *,
    selected_labels: Iterable[str] = (),
    managed_label_id: str | None = None,
) -> RegistryChange | None:
    """``RegistryChange`` für ein relevantes Ereignis, sonst None.

    Relevant: Entität angelegt/entfernt oder ihre Labels, ihr Bereich, ihr
    Gerät geändert; Gerät entfernt oder seine Labels/sein Bereich geändert;
    Bereich geändert/entfernt (das Ereignis nennt keine Felder); ein Label,
    das die Auswahl nutzt (oder das Zeitarchiv-Label), geändert/entfernt.
    Reine Namens-/Symboländerungen an Entität oder Gerät zählen nicht."""
    if not isinstance(data, Mapping):
        return None
    action = data.get("action")
    if event_type == EVENT_ENTITY:
        entity_id = data.get("entity_id")
        if not isinstance(entity_id, str):
            return None
        if action in ("create", "remove"):
            return RegistryChange(entity_id=entity_id)
        changes = _changes(data)
        if action != "update" or changes is None or not _ENTITY_FIELDS.intersection(changes):
            return None
        old = changes.get("labels")
        old_labels = frozenset(item for item in old if isinstance(item, str)) if isinstance(
            old, set | frozenset | list | tuple) else None
        return RegistryChange(entity_id=entity_id, old_labels=old_labels)
    if event_type == EVENT_DEVICE:
        device_id = data.get("device_id")
        if not isinstance(device_id, str):
            return None
        if action == "remove":
            return RegistryChange(device_id=device_id)
        changes = _changes(data)
        if action == "update" and changes is not None and _DEVICE_FIELDS.intersection(changes):
            return RegistryChange(device_id=device_id)
        return None
    if event_type == EVENT_AREA:
        return RegistryChange(wide=True) if action in ("update", "remove") else None
    if event_type == EVENT_LABEL:
        label_id = data.get("label_id")
        relevant = set(selected_labels)
        if managed_label_id:
            relevant.add(managed_label_id)
        if action in ("update", "remove") and label_id in relevant:
            return RegistryChange(wide=True)
        return None
    return None


def newly_selected(
    before: Iterable[str],
    after: Iterable[str],
    touched: Iterable[str] | None = None,
) -> list[str]:
    """Entitäten, die nach der Änderung erfasst sind und vorher nicht —
    beschränkt auf die berührten (``touched``; None = alle). Sortiert."""
    added = set(after) - set(before)
    if touched is not None:
        added &= set(touched)
    return sorted(added)
