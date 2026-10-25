"""Ledger, Verlauf und Options-Abgleich des Auswahl-Assistenten (ROADMAP 1.33).

Ohne Home-Assistant-Import testbar (Muster wie catalog.py/filtering.py). Der
Ledger merkt sich, welche Entitäten der Assistent in die Auswahl gebracht hat;
die Herkunft wird trotzdem immer neu berechnet (``compute_origin``), nie blind
aus dem Ledger geglaubt. Gespeichert wird er von selection_sync.py in einem
``Store`` (``zeitarchiv_<entry_id>_selection``).

Ledger-Form (Version 1)::

    {"entries": {entity_id: {"origin": "assistant", "mode": "label|ids",
                             "topic": str|None, "added_ts": float, "change_id": str}},
     "label_id": str|None,
     "options_snapshot": {<Filterschlüssel>: [...]} | None,
     "log": [Log-Eintrag, ...],          # neueste zuerst, höchstens LOG_LIMIT
     "pending_acks": {job_id: Ack-Body}} # intern: noch nicht quittierte Aufträge
"""

from __future__ import annotations

import re
import uuid
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

#: Die Optionsschlüssel, die die Auswahl bestimmen (alles andere, etwa
#: Nachkommastellen, gehört nicht in den Abgleich).
FILTER_KEYS = (
    CONF_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_AREAS,
    CONF_DEVICES,
    CONF_LABELS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_ENTITY_PATTERNS,
)

#: Name des vom Assistenten verwalteten Labels (erkannt wird es über die ID).
LABEL_NAME = "Zeitarchiv"

LOG_LIMIT = 200
LOG_IDS_LIMIT = 50
PENDING_ACKS_LIMIT = 50

SOURCES = frozenset({"assistant", "manual_ui", "undo", "manual_ha"})
MODES = frozenset({"label", "ids"})
RESULTS = frozenset({"ok", "already", "not_found", "excluded", "blocked", "unsupported", "error"})
STATUSES = frozenset({"applied", "partial", "failed"})

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")
_TOPIC_MAX = 40


# --------------------------------------------------------------------------- Ledger


def empty_ledger() -> dict[str, Any]:
    return {"entries": {}, "label_id": None, "options_snapshot": None, "log": [], "pending_acks": {}}


def _float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def clean_topic(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()[:_TOPIC_MAX]
    return value or None


def is_entity_id(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 255 and bool(_ENTITY_ID_RE.match(value))


def is_change_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def normalize_ledger(raw: Any) -> dict[str, Any]:
    """Liest einen gespeicherten Ledger defensiv ein. Kaputte Teile fallen weg,
    statt den Start zu stören."""
    ledger = empty_ledger()
    if not isinstance(raw, Mapping):
        return ledger
    entries = raw.get("entries")
    if isinstance(entries, Mapping):
        for entity_id, item in entries.items():
            if not is_entity_id(entity_id) or not isinstance(item, Mapping):
                continue
            mode = item.get("mode")
            if mode not in MODES:
                continue
            ledger["entries"][entity_id] = {
                "origin": "assistant",
                "mode": mode,
                "topic": clean_topic(item.get("topic")),
                "added_ts": _float(item.get("added_ts")),
                "change_id": item.get("change_id") if is_change_id(item.get("change_id")) else "",
            }
    label_id = raw.get("label_id")
    ledger["label_id"] = label_id if isinstance(label_id, str) and label_id else None
    snapshot = raw.get("options_snapshot")
    ledger["options_snapshot"] = options_snapshot(snapshot) if isinstance(snapshot, Mapping) else None
    log = raw.get("log")
    if isinstance(log, list):
        ledger["log"] = [entry for entry in log if isinstance(entry, Mapping) and is_change_id(entry.get("id"))][:LOG_LIMIT]
    pending = raw.get("pending_acks")
    if isinstance(pending, Mapping):
        ledger["pending_acks"] = {
            job_id: dict(body) for job_id, body in list(pending.items())[:PENDING_ACKS_LIMIT]
            if is_change_id(job_id) and isinstance(body, Mapping)
        }
    return ledger


# --------------------------------------------------------------------------- Options


def options_snapshot(options: Mapping[str, Any]) -> dict[str, list[str]]:
    """Die Filterschlüssel als sortierte, deduplizierte String-Listen."""
    snapshot: dict[str, list[str]] = {}
    for key in FILTER_KEYS:
        value = options.get(key)
        if isinstance(value, str):
            items: Iterable[Any] = [value]
        elif isinstance(value, list | tuple | set | frozenset):
            items = value
        else:
            items = ()
        snapshot[key] = sorted({item for item in items if isinstance(item, str)})
    return snapshot


def _signed(added: int, removed: int) -> str:
    net = added - removed
    return f"+{net}" if net > 0 else str(net)


def diff_options(
    old_snapshot: Mapping[str, Any],
    new_options: Mapping[str, Any],
    *,
    effective_before: Iterable[str] | None = None,
    effective_after: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """Zusammenfassung einer Options-Änderung als ``ha_detail`` (oder None, wenn
    sich an den Filterschlüsseln nichts geändert hat).

    ``added_entities``/``removed_entities`` zählen die effektiv erfassten
    Entitäten, wenn beide effektiven Mengen übergeben werden (so wird aus
    „ein Muster mehr“ ein „+34“), sonst nur die Einzel-IDs in ``entities``.
    Die übrigen Felder sind die Nettoänderung je Schlüssel als ``±n``."""
    old = options_snapshot(old_snapshot)
    new = options_snapshot(new_options)
    if old == new:
        return None
    changes: dict[str, tuple[int, int]] = {}
    for key in FILTER_KEYS:
        before, after = set(old[key]), set(new[key])
        changes[key] = (len(after - before), len(before - after))
    if effective_before is not None and effective_after is not None:
        before_set, after_set = set(effective_before), set(effective_after)
        added_entities, removed_entities = len(after_set - before_set), len(before_set - after_set)
    else:
        added_entities, removed_entities = changes[CONF_ENTITIES]
    parts = [
        f"{key} +{added}/-{removed}" for key, (added, removed) in changes.items() if added or removed
    ]
    return {
        "kind": "options",
        "added_entities": added_entities,
        "removed_entities": removed_entities,
        "patterns": _signed(*changes[CONF_ENTITY_PATTERNS]),
        "areas": _signed(*changes[CONF_AREAS]),
        "devices": _signed(*changes[CONF_DEVICES]),
        "labels": _signed(*changes[CONF_LABELS]),
        "excluded": _signed(
            changes[CONF_EXCLUDE_ENTITIES][0] + changes[CONF_EXCLUDE_ENTITY_PATTERNS][0],
            changes[CONF_EXCLUDE_ENTITIES][1] + changes[CONF_EXCLUDE_ENTITY_PATTERNS][1],
        ),
        "summary": "; ".join(parts)[:300],
    }


def detect_manual_change(
    ledger: dict[str, Any],
    options: Mapping[str, Any],
    now: float,
    *,
    effective_before: Iterable[str] | None = None,
    effective_after: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """Abgleich beim Setup: ändert ``ledger`` an Ort und Stelle.

    Ohne Snapshot (erster Start) wird nur der Snapshot angelegt. Weicht der
    Snapshot ab, entsteht ein ``manual_ha``-Eintrag im Verlauf, und der
    Snapshot wird nachgeführt. Gibt den neuen Log-Eintrag zurück (oder None)."""
    snapshot = ledger.get("options_snapshot")
    if snapshot is None:
        ledger["options_snapshot"] = options_snapshot(options)
        return None
    detail = diff_options(snapshot, options, effective_before=effective_before, effective_after=effective_after)
    ledger["options_snapshot"] = options_snapshot(options)
    if detail is None:
        return None
    entry = make_manual_ha_entry(detail, now)
    append_log(ledger, entry)
    return entry


# --------------------------------------------------------------------------- Verlauf


def new_change_id() -> str:
    return uuid.uuid4().hex


def job_status(results: Mapping[str, Mapping[str, Any]]) -> str:
    """applied: alles ok/already; failed: nichts davon; sonst partial."""
    if not results:
        return "failed"
    good = sum(1 for item in results.values() if item.get("result") in ("ok", "already"))
    if good == len(results):
        return "applied"
    return "failed" if good == 0 else "partial"


def make_log_entry(
    job: Mapping[str, Any],
    results: Mapping[str, Mapping[str, Any]],
    status: str,
    now: float,
) -> dict[str, Any]:
    """Log-Eintrag zu einem angewendeten Auftrag. Die ID ist die Auftrags-ID,
    damit ``undo_of`` beide meinen kann. Gespeichert werden höchstens
    LOG_IDS_LIMIT IDs samt ihren Ergebnissen, ``count`` zählt alle."""
    entity_ids = list(job.get("entity_ids") or [])
    kept = entity_ids[:LOG_IDS_LIMIT]
    mode = job.get("mode")
    if mode not in MODES:
        modes = {item.get("mode") for item in results.values() if item.get("mode") in MODES}
        mode = modes.pop() if len(modes) == 1 else None
    return {
        "id": job["id"],
        "ts": now,
        "source": job.get("source") if job.get("source") in SOURCES else "manual_ui",
        "action": job.get("action"),
        "mode": mode,
        "topic": clean_topic(job.get("topic")),
        "entity_ids": kept,
        "count": len(entity_ids),
        "status": status,
        "results": {eid: dict(results[eid]) for eid in kept if eid in results},
        "undo_of": job.get("undo_of") if is_change_id(job.get("undo_of")) else None,
        "undone_by": None,
        "ha_detail": None,
    }


def make_manual_ha_entry(detail: Mapping[str, Any], now: float, change_id: str | None = None) -> dict[str, Any]:
    count = int(detail.get("added_entities", 0)) + int(detail.get("removed_entities", 0))
    return {
        "id": change_id or new_change_id(),
        "ts": now,
        "source": "manual_ha",
        "action": "change",
        "mode": None,
        "topic": None,
        "entity_ids": [],
        "count": count,
        "status": "applied",
        "results": {},
        "undo_of": None,
        "undone_by": None,
        "ha_detail": dict(detail),
    }


def append_log(ledger: dict[str, Any], entry: dict[str, Any]) -> None:
    """Neuester Eintrag zuerst; verknüpft ein Rückgängig mit seinem Ziel
    (``undone_by``) und kappt auf LOG_LIMIT Einträge."""
    log = [item for item in ledger.get("log") or [] if item.get("id") != entry["id"]]
    undo_of = entry.get("undo_of")
    if undo_of and entry.get("status") in ("applied", "partial"):
        for item in log:
            if item.get("id") == undo_of and item.get("source") != "manual_ha" and not item.get("undone_by"):
                item["undone_by"] = entry["id"]
                break
    log.insert(0, entry)
    ledger["log"] = log[:LOG_LIMIT]


# --------------------------------------------------------------------------- Herkunft


def ledger_way_effective(
    ledger_entry: Mapping[str, Any] | None,
    explanation: Mapping[str, Any],
    label_id: str | None,
) -> bool:
    """Ob der Weg, über den der Assistent die Entität aufgenommen hat, heute
    noch wirkt (und kein Ausschluss gewinnt)."""
    if not ledger_entry or not explanation.get("selected"):
        return False
    via = explanation.get("via") or ()
    if ledger_entry.get("mode") == "label":
        return bool(label_id) and any(
            way.get("type") == "label" and way.get("level") == "entity" and way.get("value") == label_id
            for way in via
        )
    return any(way.get("type") == "entity" for way in via)


def compute_origin(
    ledger_entry: Mapping[str, Any] | None,
    explanation: Mapping[str, Any],
    label_id: str | None,
) -> dict[str, Any]:
    """``origin``/``drifted``/``topic``/``added_ts`` einer Katalogzeile.

    assistant: Ledger-Eintrag und dessen Weg wirkt; manual: erfasst ohne
    wirkenden Ledger-Eintrag; None: nicht erfasst. drifted: Ledger-Eintrag
    vorhanden, Weg wirkt nicht mehr (in HA von Hand geändert)."""
    effective = ledger_way_effective(ledger_entry, explanation, label_id)
    if explanation.get("selected"):
        origin = "assistant" if effective else "manual"
    else:
        origin = None
    return {
        "origin": origin,
        "drifted": bool(ledger_entry) and not effective,
        "topic": ledger_entry.get("topic") if ledger_entry else None,
        "added_ts": ledger_entry.get("added_ts") if ledger_entry else None,
    }
