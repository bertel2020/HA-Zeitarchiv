"""Reine Include/Exclude-Entscheidung, ohne Home-Assistant-Import.

Die Auflösung von Bereichen/Geräten zu Entity-IDs passiert in __init__.py über die
HA-Registries (braucht eine laufende Instanz) und wird VOR dem Aufruf dieser Funktion
bereits in included_entity_ids eingerechnet — hier bleibt nur noch reine Mengenlogik übrig.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase


ENTITY_PATTERN_RE = re.compile(r"^[a-z0-9_*?]+(?:\.[a-z0-9_*?]+)?$")
MAX_ENTITY_PATTERNS = 100
MAX_ENTITY_PATTERN_LENGTH = 128


def normalize_entity_patterns(
    value: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Normalisiert und validiert Entity-Glob-Muster.

    Muster ohne Punkt beziehen sich auf die Object-ID hinter der Domain,
    Muster mit Punkt auf die vollständige Entity-ID. Unterstützt werden nur
    ``*`` und ``?``; die umfangreichere fnmatch-Klammer-Syntax bleibt bewusst
    gesperrt, damit die Eingabe im Options-Flow vorhersehbar bleibt.
    """
    raw_patterns = value.splitlines() if isinstance(value, str) else (value or [])
    patterns = [pattern.strip().lower() for pattern in raw_patterns if pattern.strip()]
    patterns = list(dict.fromkeys(patterns))
    if len(patterns) > MAX_ENTITY_PATTERNS:
        raise ValueError("too_many_patterns")
    if any(
        len(pattern) > MAX_ENTITY_PATTERN_LENGTH
        or not ENTITY_PATTERN_RE.fullmatch(pattern)
        for pattern in patterns
    ):
        raise ValueError("invalid_pattern")
    return patterns


def matches_entity_pattern(entity_id: str, patterns: list[str] | tuple[str, ...]) -> bool:
    """Prüft eine Entity-ID gegen normalisierte Glob-Muster."""
    object_id = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
    return any(
        fnmatchcase(entity_id if "." in pattern else object_id, pattern)
        for pattern in patterns
    )


def is_state_value_change(old_value: str | None, new_value: str) -> bool:
    """Gibt an, ob ein ``state_changed``-Event einen neuen Wert enthält.

    Home Assistant verschickt ``state_changed`` auch dann, wenn sich nur ein
    Attribut (z. B. Friendly Name, Einheit oder State Class) geändert hat.
    Für ein Zeitreihenarchiv ist das kein neuer Messpunkt. ``None`` steht hier
    ausschließlich für ein fehlendes ``old_state`` und lässt den Initialwert
    beim ersten Auftauchen einer Entität weiterhin durch.
    """
    return old_value is None or old_value != new_value


def should_archive(
    entity_id: str,
    domain: str,
    included_entity_ids: set[str],
    included_domains: set[str],
    excluded_entity_ids: set[str],
    included_entity_patterns: list[str] | tuple[str, ...] = (),
    excluded_entity_patterns: list[str] | tuple[str, ...] = (),
) -> bool:
    """Entscheidet, ob eine Entität archiviert werden soll.

    Exakte und musterbasierte Ausschlüsse gewinnen immer. Danach reicht eine
    explizite Entity-ID, eine ausgewählte Domain oder ein Einschlussmuster.
    """
    if entity_id in excluded_entity_ids or matches_entity_pattern(
        entity_id, excluded_entity_patterns
    ):
        return False
    return (
        entity_id in included_entity_ids
        or domain in included_domains
        or matches_entity_pattern(entity_id, included_entity_patterns)
    )
