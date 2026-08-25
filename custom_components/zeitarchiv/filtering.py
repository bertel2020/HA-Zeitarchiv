"""Reine Include/Exclude-Entscheidung, ohne Home-Assistant-Import.

Die Auflösung von Bereichen/Geräten zu Entity-IDs passiert in __init__.py über die
HA-Registries (braucht eine laufende Instanz) und wird VOR dem Aufruf dieser Funktion
bereits in included_entity_ids eingerechnet — hier bleibt nur noch reine Mengenlogik übrig.
"""

from __future__ import annotations


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
) -> bool:
    """Entscheidet, ob eine Entität archiviert werden soll.

    Exclude gewinnt immer. Danach: explizit genannte Entity-ID ODER eine
    ausgewählte Domain reicht für Include (genau wie InfluxDBs
    include/exclude-per-Domain/Entity/Glob-Logik, nur ohne Glob-Teil —
    der wird in Zeitarchiv durch EntitySelector/AreaSelector/DeviceSelector
    im Options-Flow ersetzt, siehe Konzept Abschnitt 03).
    """
    if entity_id in excluded_entity_ids:
        return False
    return entity_id in included_entity_ids or domain in included_domains
