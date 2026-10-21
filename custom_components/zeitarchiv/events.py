"""Reine Event-Aufbereitung, ohne Home-Assistant-Import.

Getrennt von __init__.py gehalten, damit sich die eigentliche Entscheidungslogik
(welcher Zustand wird wie archiviert) ohne laufende Home-Assistant-Instanz testen lässt.
"""

from __future__ import annotations

import re
import uuid

from .const import (
    APP_ENTITY_ID_MAX_LENGTH,
    APP_EVENT_TEXT_MAX_LENGTH,
    IGNORED_STATES,
    PRESENCE_DOMAINS,
    SWITCH_DOMAINS,
)

# Spiegel von ENTITY_ID_PATTERN der App (storage/paths.py). Home Assistant
# erlaubt bis zu 255 Zeichen, die App nur 240 — eine längere ID würde dort mit
# 422 abgelehnt und mit ihr der komplette Batch.
_APP_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")


def _event_text(value: object) -> str | None:
    """Attributwert als Text in den Grenzen der App, sonst None.

    Attribute sind in Home Assistant beliebige Objekte. Ein Nicht-String oder
    ein überlanger Text liefe in der App in einen 422 — gekürzt statt
    verworfen, weil der Messwert selbst gültig ist.
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text[:APP_EVENT_TEXT_MAX_LENGTH]


def is_text_state(domain: str, state: str) -> bool:
    """Ob build_event() diesen Zustand allein deshalb verwirft, weil er Text ist.

    Grundlage für den Hinweis an den Nutzer (Repair-Karte, siehe repairs.py):
    eine ausgewählte Entität, die nur Text liefert (z. B. "Heating"/"Idle"
    oder ein Waschprogramm), kommt nie in der App an und taucht dort deshalb
    auch nicht in der Auswahl auf. Vorübergehende Zustände wie "unavailable"
    zählen nicht — die verwirft build_event() bei jeder Entität.
    """
    normalized_state = state.strip().lower()
    if normalized_state in IGNORED_STATES:
        return False
    if domain in SWITCH_DOMAINS or domain in PRESENCE_DOMAINS:
        return False
    try:
        float(state)
    except (TypeError, ValueError):
        return True
    return False


def build_event(
    entity_id: str,
    domain: str,
    state: str,
    state_class: str | None,
    unit: str | None,
    timestamp: float,
    friendly_name: str | None = None,
    decimal_places: int = 3,
    *,
    allow_text: bool = False,
    state_label: str | None = None,
) -> dict | None:
    """Baut das Event-Payload für die Queue, oder None wenn der Zustand verworfen wird.

    Schalter-Domains (SWITCH_DOMAINS: binary_sensor/switch/input_boolean/light/…)
    werden auf 1/0 normalisiert.
    Anwesenheits-Domains (device_tracker/person) ebenso, aber mit eigenem
    State-Vokabular: "home" → 1, alles andere (auch eine benannte Zone
    ungleich "home") → 0.
    Alles andere muss sich als float parsen lassen (Standard- und Zähler-Entitäten).

    allow_text=True (einzeln ausgewählte Entität UND die App meldet die
    Fähigkeit "state"): ein Text-Zustand geht als ``state`` statt ``value``
    hinaus, mit ``state_label`` als HA-Übersetzung; die App bildet ihn auf
    einen Index ab (Typ "state"). Dann gehen auch "unavailable"/"unknown" als
    ``state`` hinaus — ob sie zählen, entscheidet die App (nur bei einer schon
    bestehenden Zustands-Entität). Ohne allow_text bleibt alles wie bisher:
    Text wird verworfen.
    """
    if len(entity_id) > APP_ENTITY_ID_MAX_LENGTH or not _APP_ENTITY_ID_RE.fullmatch(entity_id):
        return None

    normalized_state = state.strip().lower()
    if normalized_state in IGNORED_STATES:
        if allow_text and normalized_state in ("unavailable", "unknown"):
            return _payload(entity_id, domain, timestamp, state_class, unit, friendly_name,
                            state=normalized_state)
        return None

    if domain in SWITCH_DOMAINS:
        if normalized_state not in ("on", "off"):
            return None
        value = 1.0 if normalized_state == "on" else 0.0
    elif domain in PRESENCE_DOMAINS:
        value = 1.0 if normalized_state == "home" else 0.0
    else:
        try:
            # Die Integration begrenzt die uebertragenen Messwerte bereits an
            # der Quelle (Options-Flow: Nachkommastellen). Dadurch landen
            # weder Anzeige-Artefakte noch mehr fachlich relevante
            # Nachkommastellen als konfiguriert in der App.
            value = round(float(state), decimal_places)
        except (TypeError, ValueError):
            if not allow_text:
                return None
            return _payload(entity_id, domain, timestamp, state_class, unit, friendly_name,
                            state=state.strip(), state_label=state_label)

    return _payload(entity_id, domain, timestamp, state_class, unit, friendly_name, value=value)


def _payload(
    entity_id: str,
    domain: str,
    timestamp: float,
    state_class: str | None,
    unit: str | None,
    friendly_name: str | None,
    *,
    value: float | None = None,
    state: str | None = None,
    state_label: str | None = None,
) -> dict:
    payload = {
        # Bleibt vom Enqueue bis über alle HTTP-Retries stabil. Der Server
        # persistiert diese ID und kann dadurch eine verlorene HTTP-Antwort
        # wiederholen, ohne denselben Messwert doppelt anzuhängen.
        "event_id": uuid.uuid4().hex,
        "entity_id": entity_id,
        "domain": _event_text(domain),
        "ts": timestamp,
        "value": value,
        "state_class": _event_text(state_class),
        "unit": _event_text(unit),
        "friendly_name": _event_text(friendly_name),
    }
    if state is not None:
        # Nur bei Text-Zuständen: eine ältere App ignorierte die Felder,
        # bekäme dann aber auch kein value — deshalb schickt __init__.py
        # Text nur, wenn die App die Fähigkeit "state" meldet.
        del payload["value"]
        payload["state"] = _event_text(state)
        if state_label and state_label != state:
            payload["state_label"] = _event_text(state_label)
    return payload
