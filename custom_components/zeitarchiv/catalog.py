"""Katalog der archivierbaren Entitäten für den Auswahl-Assistenten (ROADMAP 1.33).

Die App sieht nur Entitäten, die schon Werte geschickt haben, und kennt weder
Geräteklasse noch Bereich, Gerät oder Energie-Dashboard. Die Integration baut
deshalb aus States und Registries eine Liste reiner Metadaten (keine Werte) und
schickt sie an die App, die daraus Vorschläge ableitet. Der Katalog verlässt das
Haus nicht: er geht nur an die eigene App.

Die Aufbereitung ist ohne Home-Assistant-Import testbar. Die Registry-Zugriffe
laufen über kleine Funktionen, die Registries werden von außen hereingereicht.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .events import is_text_state
from .selection_ledger import LOG_LIMIT, compute_origin

#: Domains, aus denen die Integration Zustände archivieren kann. Alles andere
#: (Kameras, Updates, Text-Eingaben …) wäre als Vorschlag nutzlos.
CATALOG_DOMAINS = frozenset({
    "sensor", "binary_sensor", "number", "input_number", "counter", "weather",
    "switch", "input_boolean", "light", "fan", "automation", "script", "remote",
    "siren", "humidifier", "update", "calendar", "climate", "water_heater",
    "device_tracker", "person", "lock", "cover", "vacuum", "lawn_mower",
})

#: Mehr nimmt die App je Katalog nicht an (siehe selection_routes.MAX_ENTITIES).
MAX_ENTITIES = 20_000

#: Body-Grenze mit Abstand zum 8-MB-Limit von nginx vor der App.
MAX_BODY_BYTES = 7_500_000

#: Rollen aus den Energie-Einstellungen (Schlüssel der Statistik-ID → Rolle).
_ENERGY_ROLE_PRIORITY = (
    "grid_import", "grid_export", "grid_power", "solar", "battery_in",
    "battery_out", "gas", "water", "consumer", "water_consumer",
)


def energy_roles_from_prefs(prefs: Mapping[str, Any] | None) -> dict[str, str]:
    """Entity-ID → Rolle aus den Energie-Einstellungen von Home Assistant.

    Statistik-IDs externer Statistiken ("domain:name") sind keine Entitäten und
    fallen heraus. Fehlt oder ist etwas kaputt, gilt: keine Rolle — der Katalog
    funktioniert auch ohne Energie-Dashboard."""
    roles: dict[str, str] = {}
    if not isinstance(prefs, Mapping):
        return roles

    def put(entity_id: object, role: str) -> None:
        if isinstance(entity_id, str) and "." in entity_id and ":" not in entity_id:
            roles.setdefault(entity_id, role)

    for source in prefs.get("energy_sources") or ():
        if not isinstance(source, Mapping):
            continue
        kind = source.get("type")
        if kind == "grid":
            for flow in source.get("flow_from") or ():
                put(flow.get("stat_energy_from"), "grid_import")
                put(flow.get("stat_rate"), "grid_power")
            for flow in source.get("flow_to") or ():
                put(flow.get("stat_energy_to"), "grid_export")
            put(source.get("power_config", {}).get("stat_rate") if isinstance(source.get("power_config"), Mapping) else None, "grid_power")
        elif kind == "solar":
            put(source.get("stat_energy_from"), "solar")
            put(source.get("stat_rate"), "solar")
        elif kind == "battery":
            put(source.get("stat_energy_from"), "battery_out")
            put(source.get("stat_energy_to"), "battery_in")
            put(source.get("stat_rate"), "battery_out")
        elif kind == "gas":
            put(source.get("stat_energy_from"), "gas")
        elif kind == "water":
            put(source.get("stat_energy_from"), "water")
    for device in prefs.get("device_consumption") or ():
        if isinstance(device, Mapping):
            put(device.get("stat_consumption"), "consumer")
            put(device.get("stat_rate"), "consumer")
    for device in prefs.get("device_consumption_water") or ():
        if isinstance(device, Mapping):
            put(device.get("stat_consumption"), "water_consumer")
    return roles


def _text(value: object, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    return text[:limit] if text else None


def _name(obj: Any) -> str | None:
    return _text(getattr(obj, "name_by_user", None) or getattr(obj, "name", None))


def _explain(matcher: Any, entity_id: str) -> dict[str, Any]:
    """``matcher.explain`` oder — bei einem Matcher ohne (Tests, Altbestand) —
    dieselbe Aussage aus ``matches`` ohne Wege."""
    explain = getattr(matcher, "explain", None)
    if callable(explain):
        return explain(entity_id)
    selected = bool(matcher.matches(entity_id))
    excluded = (not selected) and bool(matcher.matches(entity_id, apply_exclusions=False))
    return {"selected": selected, "excluded": excluded, "via": [], "excluded_by": []}


def build_catalog(
    states: Iterable[Any],
    entity_registry: Any,
    device_registry: Any,
    area_registry: Any,
    matcher: Any,
    energy_roles: Mapping[str, str] | None = None,
    *,
    ledger: Mapping[str, Any] | None = None,
    label_registry: Any = None,
) -> list[dict[str, Any]]:
    """Eine Zeile je archivierbarer Entität, ohne Werte.

    ``selected`` heißt: der Filter erfasst die Entität heute. ``excluded``:
    sie wäre erfasst, steht aber in den Ausschlüssen. Deaktivierte Entitäten
    liefert HA ohnehin nicht als State; versteckte kommen mit ``hidden``.

    Phase 1: ``via`` (alle wirkenden Wege, leer wenn nicht erfasst),
    ``excluded_by`` (greifende Ausschlüsse, auch ohne Einschluss — die
    Vorschläge sperren solche Zeilen), ``text``, sowie aus dem ``ledger``
    ``origin``/``drifted``/``topic``/``added_ts`` (selection_ledger.compute_origin)."""
    roles = energy_roles or {}
    entries = (ledger or {}).get("entries") or {}
    label_id = (ledger or {}).get("label_id")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    def area_name(area_id: str | None) -> str | None:
        if not area_id:
            return None
        area = area_registry.async_get_area(area_id)
        return _text(getattr(area, "name", None))

    def label_name(value: str) -> str:
        label = label_registry.async_get_label(value) if label_registry is not None else None
        return _text(getattr(label, "name", None)) or value

    def way(item: Mapping[str, Any]) -> dict[str, Any]:
        kind = item.get("type")
        value = item.get("value")
        if kind == "area":
            return {"type": "area", "value": area_name(value) or value}
        if kind == "device":
            device = device_registry.async_get(value) if value else None
            return {"type": "device", "value": _name(device) or value}
        if kind == "label":
            return {"type": "label", "value": label_name(value), "level": item.get("level")}
        if kind == "pattern":
            return {"type": "pattern", "value": value}
        return {"type": "entity"}

    def add(entity_id: str, state: Any | None) -> None:
        domain = entity_id.split(".", 1)[0]
        if domain not in CATALOG_DOMAINS or entity_id in seen or len(rows) >= MAX_ENTITIES:
            return
        seen.add(entity_id)
        entry = entity_registry.async_get(entity_id)
        attrs = state.attributes if state is not None else {}
        device = device_registry.async_get(entry.device_id) if entry is not None and entry.device_id else None
        explanation = _explain(matcher, entity_id)
        selected = bool(explanation.get("selected"))
        ledger_entry = entries.get(entity_id)
        origin = compute_origin(ledger_entry, explanation, label_id)
        via = [way(item) for item in explanation.get("via") or ()] if selected else []
        if origin["origin"] == "assistant":
            via.append({"type": "assistant", "topic": origin["topic"], "mode": ledger_entry.get("mode")})
        raw_state = getattr(state, "state", None)
        rows.append({
            "entity_id": entity_id,
            "name": _text(attrs.get("friendly_name") or getattr(entry, "name", None) or getattr(entry, "original_name", None)),
            "domain": domain,
            "device_class": _text(
                attrs.get("device_class") or getattr(entry, "device_class", None) or getattr(entry, "original_device_class", None), 40
            ),
            "state_class": _text(attrs.get("state_class"), 40),
            "unit": _text(attrs.get("unit_of_measurement"), 40),
            "platform": _text(getattr(entry, "platform", None), 80),
            "device": _name(device),
            "area": area_name(getattr(entry, "area_id", None) or getattr(device, "area_id", None)),
            "entity_category": _text(getattr(entry, "entity_category", None), 20),
            "hidden": bool(getattr(entry, "hidden_by", None)),
            "energy_role": roles.get(entity_id),
            "selected": selected,
            "excluded": bool(explanation.get("excluded")) and not selected,
            "text": isinstance(raw_state, str) and is_text_state(domain, raw_state),
            "via": via,
            "excluded_by": [way(item) for item in explanation.get("excluded_by") or ()],
            **origin,
        })

    for state in states:
        add(state.entity_id, state)
    rows.sort(key=lambda row: row["entity_id"])
    return rows


def build_catalog_body(
    rows: list[dict[str, Any]],
    ledger: Mapping[str, Any] | None,
    label_name: str | None = None,
) -> dict[str, Any]:
    """Der erweiterte Body für POST /api/catalog (Phase 1)."""
    ledger = ledger or {}
    label_id = ledger.get("label_id")
    return {
        "entities": rows,
        "label": {"id": label_id, "name": label_name or label_id} if label_id else None,
        "log": list(ledger.get("log") or [])[:LOG_LIMIT],
        "ledger_count": len(ledger.get("entries") or {}),
    }


def encode_catalog(body: Mapping[str, Any], limit: int = MAX_BODY_BYTES) -> bytes:
    """Kompakt als JSON kodiert und unter ``limit`` gehalten: zu groß, fallen
    zuerst nicht erfasste Zeilen ohne Ledger-Bezug weg (vom Ende her), dann
    notfalls der Verlauf. Erfasste Entitäten bleiben so lange wie möglich."""
    def dump(payload: Mapping[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    encoded = dump(body)
    if len(encoded) <= limit:
        return encoded
    rows = list(body.get("entities") or [])
    def important(row: Mapping[str, Any]) -> bool:
        return bool(row.get("selected") or row.get("origin") or row.get("drifted") or row.get("excluded_by"))

    keep = [row for row in rows if important(row)]
    rest = [row for row in rows if not important(row)]
    while rest:
        rest = rest[: len(rest) // 2]
        encoded = dump({**body, "entities": sorted(keep + rest, key=lambda row: row["entity_id"])})
        if len(encoded) <= limit:
            return encoded
    trimmed = {**body, "entities": keep}
    encoded = dump(trimmed)
    if len(encoded) > limit:
        encoded = dump({**trimmed, "log": []})
    return encoded


def catalog_digest(rows: list[dict[str, Any]]) -> str:
    """Stabiler Fingerabdruck: ein unveränderter Katalog wird nicht erneut gesendet."""
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
