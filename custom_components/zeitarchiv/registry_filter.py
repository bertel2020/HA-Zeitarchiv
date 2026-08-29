"""Dynamische Auflösung der Home-Assistant-Registry-Filter.

Das Modul importiert Home Assistant bewusst nicht direkt. Dadurch bleibt die
Auswahllogik mit kleinen Registry-Doubles testbar. Die echten Registry-Objekte
werden beim Setup injiziert und bleiben live: spätere Label-, Bereichs- oder
Geräteänderungen sind damit ohne Reload sofort wirksam.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .const import (
    CONF_AREAS,
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_ENTITY_PATTERNS,
    CONF_LABELS,
)
from .filtering import should_archive

LEGACY_CONF_DOMAINS = "domains"


def migrate_legacy_domains(
    options: Mapping[str, Any], known_entity_ids: Iterable[str]
) -> dict[str, Any]:
    """Ersetzt alte Domainfilter einmalig durch konkrete Entity-IDs."""
    migrated = dict(options)
    legacy_domains = set(migrated.pop(LEGACY_CONF_DOMAINS, []))
    if not legacy_domains:
        return migrated

    entities = list(migrated.get(CONF_ENTITIES, []))
    entities.extend(
        entity_id
        for entity_id in sorted(set(known_entity_ids))
        if entity_id.split(".", 1)[0] in legacy_domains
    )
    migrated[CONF_ENTITIES] = list(dict.fromkeys(entities))
    return migrated


class ArchiveFilterMatcher:
    """Prüft Filter gegen die jeweils aktuellen Registry-Einträge."""

    def __init__(
        self,
        options: Mapping[str, Any],
        entity_registry: Any,
        device_registry: Any,
        area_registry: Any,
    ) -> None:
        self.included_entities = set(options.get(CONF_ENTITIES, []))
        self.excluded_entities = set(options.get(CONF_EXCLUDE_ENTITIES, []))
        self.included_patterns = list(options.get(CONF_ENTITY_PATTERNS, []))
        self.excluded_patterns = list(options.get(CONF_EXCLUDE_ENTITY_PATTERNS, []))
        self.selected_labels = set(options.get(CONF_LABELS, []))
        self.selected_areas = set(options.get(CONF_AREAS, []))
        self.selected_devices = set(options.get(CONF_DEVICES, []))
        self._entity_registry = entity_registry
        self._device_registry = device_registry
        self._area_registry = area_registry

    def _included_by_registry(self, entity_id: str) -> bool:
        entry = self._entity_registry.async_get(entity_id)
        if entry is None:
            return False

        if self.selected_labels.intersection(entry.labels):
            return True

        device = (
            self._device_registry.async_get(entry.device_id)
            if entry.device_id
            else None
        )
        if entry.device_id in self.selected_devices:
            return True
        if device is not None and self.selected_labels.intersection(device.labels):
            return True

        effective_area = entry.area_id or (device.area_id if device else None)
        if effective_area in self.selected_areas:
            return True
        if effective_area is None:
            return False
        area = self._area_registry.async_get_area(effective_area)
        return area is not None and bool(self.selected_labels.intersection(area.labels))

    def matches(self, entity_id: str, *, apply_exclusions: bool = True) -> bool:
        """Gibt zurück, ob eine Entity vom aktuellen Filter erfasst wird."""
        return should_archive(
            entity_id,
            self.included_entities,
            self.excluded_entities if apply_exclusions else set(),
            self.included_patterns,
            self.excluded_patterns if apply_exclusions else (),
            included_by_registry=self._included_by_registry(entity_id),
        )
