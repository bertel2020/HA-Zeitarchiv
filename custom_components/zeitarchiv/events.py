"""Reine Event-Aufbereitung, ohne Home-Assistant-Import.

Getrennt von __init__.py gehalten, damit sich die eigentliche Entscheidungslogik
(welcher Zustand wird wie archiviert) ohne laufende Home-Assistant-Instanz testen lässt.
"""

from __future__ import annotations

import uuid

from .const import IGNORED_STATES, SWITCH_DOMAINS


def build_event(
    entity_id: str,
    domain: str,
    state: str,
    state_class: str | None,
    unit: str | None,
    timestamp: float,
    friendly_name: str | None = None,
) -> dict | None:
    """Baut das Event-Payload für die Queue, oder None wenn der Zustand verworfen wird.

    Schalter-Domains (binary_sensor/switch/input_boolean) werden auf 1/0 normalisiert.
    Alles andere muss sich als float parsen lassen (Standard- und Zähler-Entitäten) —
    nicht-numerische Text-Sensoren werden in Phase 1 bewusst nicht archiviert, weil das
    Speicherformat aus dem Konzept (timestamp, value) dafür nicht ausgelegt ist.
    """
    normalized_state = state.strip().lower()
    if normalized_state in IGNORED_STATES:
        return None

    if domain in SWITCH_DOMAINS:
        if normalized_state not in ("on", "off"):
            return None
        value = 1.0 if normalized_state == "on" else 0.0
    else:
        try:
            # Die Integration begrenzt die uebertragenen Messwerte bereits an
            # der Quelle. Dadurch landen weder Anzeige-Artefakte noch mehr als
            # drei fachlich relevante Nachkommastellen in der App.
            value = round(float(state), 3)
        except (TypeError, ValueError):
            return None

    return {
        # Bleibt vom Enqueue bis über alle HTTP-Retries stabil. Der Server
        # persistiert diese ID und kann dadurch eine verlorene HTTP-Antwort
        # wiederholen, ohne denselben Messwert doppelt anzuhängen.
        "event_id": uuid.uuid4().hex,
        "entity_id": entity_id,
        "domain": domain,
        "ts": timestamp,
        "value": value,
        "state_class": state_class,
        "unit": unit,
        "friendly_name": friendly_name,
    }
