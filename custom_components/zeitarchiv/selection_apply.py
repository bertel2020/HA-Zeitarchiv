"""Anwendung von Auswahl-Aufträgen der App auf Optionen und Registry (ROADMAP 1.33).

Ohne Home-Assistant-Import testbar: alle Registry- und State-Zugriffe laufen
über ``SelectionPorts`` (in selection_sync.py mit den echten Registries
belegt, in Tests mit Fakes). Ein Durchgang wendet alle abgeholten Aufträge
nacheinander auf EINE Arbeitskopie der Optionen an; ob sich daran etwas
geändert hat, entscheidet der Aufrufer (ein einziges ``async_update_entry``).

Die Label-Änderungen passieren hier sofort über die Ports (erster Schritt der
Reihenfolge laut Vertrag); Ledger, Snapshot und Verlauf werden nur im
übergebenen Ledger-Dict geändert, gespeichert wird draußen.

Phase 2: ``exclude``/``include`` (Einzel-Ausschluss setzen/aufheben),
``add`` mit ``unexclude_ids`` und ``add_patterns``/``remove_patterns``
(Include-Muster; der Assistent entfernt nur Muster, die er selbst angelegt hat).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .catalog import CATALOG_DOMAINS
from .const import (
    CONF_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_ENTITY_PATTERNS,
    CONF_LABELS,
)
from .filtering import (
    MAX_ENTITY_PATTERN_LENGTH,
    MAX_ENTITY_PATTERNS,
    matches_entity_pattern,
    normalize_entity_patterns,
)
from .selection_ledger import (
    FILTER_KEYS,
    PENDING_ACKS_LIMIT,
    append_log,
    clean_topic,
    is_change_id,
    is_entity_id,
    job_status,
    make_log_entry,
    options_snapshot,
)

#: Mehr IDs nimmt die Integration je Auftrag nicht an (wie die App).
MAX_JOB_IDS = 200
#: Mehr Muster je Auftrag ebenso nicht (Phase 2).
MAX_JOB_PATTERNS = 20

_JOB_SOURCES = frozenset({"assistant", "manual_ui", "undo"})
ENTITY_ACTIONS = frozenset({"add", "remove", "exclude", "include"})
PATTERN_ACTIONS = frozenset({"add_patterns", "remove_patterns"})


class SelectionPorts(Protocol):
    """Was die Anwendung von Home Assistant braucht."""

    def known(self, entity_id: str) -> bool:
        """Entität existiert (Registry-Eintrag oder aktueller Zustand)."""

    def has_registry_entry(self, entity_id: str) -> bool: ...

    def is_text(self, entity_id: str) -> bool:
        """Aktueller Zustand ist reiner Text (events.is_text_state)."""

    def entity_labels(self, entity_id: str) -> set[str]: ...

    def set_entity_labels(self, entity_id: str, labels: set[str]) -> None:
        """Darf werfen; das Ergebnis der Entität wird dann ``error``."""

    def ensure_label(self, known_label_id: str | None) -> str:
        """Das verwaltete Label finden (gespeicherte ID, sonst Name) oder anlegen."""

    def is_selected(self, entity_id: str, options: Mapping[str, Any]) -> bool:
        """Ob die Entität mit diesen Optionen (und den Live-Registries) erfasst ist."""


@dataclass
class ApplyOutcome:
    options: dict[str, Any]
    options_changed: bool
    acks: list[dict[str, Any]] = field(default_factory=list)
    log_entries: list[dict[str, Any]] = field(default_factory=list)
    #: Entitäten, die gerade das Label bekommen haben (Zustand nachsenden).
    label_targets: list[str] = field(default_factory=list)
    #: Wieder aufgenommene Entitäten, die jetzt erfasst sind (Zustand nachsenden).
    include_targets: list[str] = field(default_factory=list)
    #: Neu angelegte Include-Muster (die Glue-Schicht sucht die Treffer, pattern_targets).
    added_patterns: list[str] = field(default_factory=list)
    #: Aufträge, die nicht angewendet wurden (abgelaufen, schon quittiert …).
    skipped: list[str] = field(default_factory=list)


def _id_list(raw: Any) -> list[str]:
    return list(dict.fromkeys(item for item in raw if isinstance(item, str))) if isinstance(raw, list) else []


def normalize_job(raw: Any, now: float) -> tuple[dict[str, Any] | None, str | None]:
    """Prüft einen Auftrag der App. Liefert (Auftrag, None), (None, Fehlertext)
    für einen ungültigen Auftrag mit brauchbarer ID oder (None, None), wenn er
    stillschweigend übergangen wird (keine ID, abgelaufen)."""
    if not isinstance(raw, Mapping) or not is_change_id(raw.get("id")):
        return None, None
    expires = raw.get("expires_ts")
    if isinstance(expires, int | float) and not isinstance(expires, bool) and expires < now:
        return None, None
    action = raw.get("action")
    if action not in ENTITY_ACTIONS and action not in PATTERN_ACTIONS:
        return None, "invalid_action"
    source = raw.get("source")
    if source not in _JOB_SOURCES:
        return None, "invalid_source"
    mode = raw.get("mode")
    if action == "add":
        if mode not in ("label", "ids"):
            return None, "invalid_mode"
    elif action == "add_patterns":
        mode = "ids"  # die Muster liegen in den Optionen
    else:
        mode = "auto"
    patterns: list[str] = []
    entity_ids: list[str] = []
    if action in PATTERN_ACTIONS:
        raw_patterns = raw.get("patterns")
        if not isinstance(raw_patterns, list) or not raw_patterns:
            return None, "invalid_patterns"
        if any(not isinstance(item, str) or not item.strip() or len(item) > MAX_ENTITY_PATTERN_LENGTH for item in raw_patterns):
            return None, "invalid_patterns"
        patterns = list(dict.fromkeys(raw_patterns))
        if len(patterns) > MAX_JOB_PATTERNS:
            return None, "invalid_patterns"
    else:
        entity_ids = _id_list(raw.get("entity_ids"))
        if not entity_ids or len(entity_ids) > MAX_JOB_IDS:
            return None, "invalid_entity_ids"
    force_ids = [item for item in _id_list(raw.get("force_ids")) if item in entity_ids]
    unexclude_ids = (
        [item for item in _id_list(raw.get("unexclude_ids")) if item in entity_ids] if action == "add" else []
    )
    undo_of = raw.get("undo_of")
    return {
        "id": raw["id"],
        "source": source,
        "action": action,
        "mode": mode,
        "topic": clean_topic(raw.get("topic")),
        "entity_ids": entity_ids,
        "force_ids": force_ids,
        "unexclude_ids": unexclude_ids,
        "patterns": patterns,
        "undo_of": undo_of if is_change_id(undo_of) else None,
    }, None


def _copy_options(options: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(options)
    for key in FILTER_KEYS:
        value = copied.get(key)
        copied[key] = list(value) if isinstance(value, list | tuple | set | frozenset) else []
    return copied


def is_pattern_excluded(entity_id: str, options: Mapping[str, Any]) -> bool:
    return matches_entity_pattern(entity_id, list(options.get(CONF_EXCLUDE_ENTITY_PATTERNS) or ()))


def is_excluded(entity_id: str, options: Mapping[str, Any]) -> bool:
    return entity_id in (options.get(CONF_EXCLUDE_ENTITIES) or ()) or is_pattern_excluded(entity_id, options)


def pattern_targets(
    candidates: Iterable[str],
    patterns: list[str],
    options: Mapping[str, Any],
    *,
    is_text: Callable[[str], bool],
    was_selected: Callable[[str], bool],
) -> list[str]:
    """Entitäten, die durch neu angelegte Muster jetzt erst erfasst sind und
    deren Zustand nachgesendet wird: passend, nicht ausgeschlossen, keine
    Textentität (Muster holen nie Text, ``_text_allowed``) und vorher nicht
    schon erfasst."""
    if not patterns:
        return []
    return [
        entity_id for entity_id in dict.fromkeys(candidates)
        if matches_entity_pattern(entity_id, patterns)
        and not is_excluded(entity_id, options)
        and not is_text(entity_id)
        and not was_selected(entity_id)
    ]


class _Run:
    def __init__(self, ledger: dict[str, Any], ports: SelectionPorts, options: dict[str, Any], now: float) -> None:
        self.ledger = ledger
        self.ports = ports
        self.options = options
        self.now = now
        self.label_targets: list[str] = []
        self.include_targets: list[str] = []
        self.added_patterns: list[str] = []

    def label_id(self) -> str:
        label_id = self.ports.ensure_label(self.ledger.get("label_id"))
        self.ledger["label_id"] = label_id
        return label_id

    def add(self, entity_id: str, job: Mapping[str, Any]) -> dict[str, Any]:
        if not is_entity_id(entity_id) or not self.ports.known(entity_id):
            return {"result": "not_found", "mode": None}
        if entity_id.split(".", 1)[0] not in CATALOG_DOMAINS:
            return {"result": "blocked", "mode": None}
        unexcluded = False
        if entity_id in job.get("unexclude_ids", ()) and not is_pattern_excluded(entity_id, self.options):
            # Ausdrücklich bestätigt: den Einzel-Ausschluss zuerst aufheben.
            # Ein Muster-Ausschluss bleibt (dann unten ``excluded``).
            excluded = self.options[CONF_EXCLUDE_ENTITIES]
            while entity_id in excluded:
                excluded.remove(entity_id)
                unexcluded = True
        if is_excluded(entity_id, self.options):
            return {"result": "excluded", "mode": None}
        entries = self.ledger["entries"]
        if self.ports.is_selected(entity_id, self.options):
            existing = entries.get(entity_id)
            mode = existing.get("mode") if existing else None
            # Nach dem Aufheben schon über einen anderen Weg erfasst: geändert hat sich trotzdem etwas.
            return {"result": "ok" if unexcluded else "already", "mode": mode}
        use_label = (
            job["mode"] == "label"
            and entity_id not in job["force_ids"]
            and self.ports.has_registry_entry(entity_id)
            and not self.ports.is_text(entity_id)
        )
        if use_label:
            label_id = self.label_id()
            labels = set(self.ports.entity_labels(entity_id))
            if label_id not in labels:
                self.ports.set_entity_labels(entity_id, labels | {label_id})
            if label_id not in self.options[CONF_LABELS]:
                self.options[CONF_LABELS].append(label_id)
            self.label_targets.append(entity_id)
            mode = "label"
        else:
            if entity_id not in self.options[CONF_ENTITIES]:
                self.options[CONF_ENTITIES].append(entity_id)
            mode = "ids"
        entries[entity_id] = {
            "origin": "assistant",
            "mode": mode,
            "topic": job.get("topic"),
            "added_ts": self.now,
            "change_id": job["id"],
        }
        return {"result": "ok", "mode": mode}

    def _drop_label(self, entity_id: str) -> bool:
        label_id = self.ledger.get("label_id")
        if not label_id or not self.ports.has_registry_entry(entity_id):
            return False
        labels = set(self.ports.entity_labels(entity_id))
        if label_id not in labels:
            return False
        self.ports.set_entity_labels(entity_id, labels - {label_id})
        return True

    def remove(self, entity_id: str) -> dict[str, Any]:
        if not is_entity_id(entity_id):
            return {"result": "not_found", "mode": None}
        entries = self.ledger["entries"]
        entities = self.options[CONF_ENTITIES]
        existing = entries.get(entity_id)
        if existing is not None:
            if existing["mode"] == "label":
                self._drop_label(entity_id)
            elif entity_id in entities:
                entities.remove(entity_id)
            del entries[entity_id]
            return {"result": "ok", "mode": existing["mode"]}
        if entity_id in entities:
            entities.remove(entity_id)
            return {"result": "ok", "mode": "ids"}
        # Das verwaltete Label, von Hand in HA gesetzt: gehört trotzdem uns.
        if self._drop_label(entity_id):
            return {"result": "ok", "mode": "label"}
        if self.ports.is_selected(entity_id, self.options):
            return {"result": "unsupported", "mode": None}
        return {"result": "already", "mode": None}

    def exclude(self, entity_id: str) -> dict[str, Any]:
        """Einzel-Ausschluss setzen. Auch für (noch) unbekannte Entitäten
        erlaubt; archivierte Daten und Ledger-Einträge bleiben."""
        if not is_entity_id(entity_id):
            return {"result": "not_found", "mode": None}
        excluded = self.options[CONF_EXCLUDE_ENTITIES]
        if entity_id in excluded:
            return {"result": "already", "mode": None}
        excluded.append(entity_id)
        return {"result": "ok", "mode": None}

    def include(self, entity_id: str) -> dict[str, Any]:
        """Wieder aufnehmen = nur „nicht mehr ausgeschlossen“. Gegen ein
        Ausschlussmuster hilft das nicht (``blocked``, nichts geändert)."""
        if not is_entity_id(entity_id):
            return {"result": "not_found", "mode": None}
        if is_pattern_excluded(entity_id, self.options):
            return {"result": "blocked", "mode": None}
        excluded = self.options[CONF_EXCLUDE_ENTITIES]
        if entity_id not in excluded:
            return {"result": "already", "mode": None}
        while entity_id in excluded:
            excluded.remove(entity_id)
        if self.ports.is_selected(entity_id, self.options):
            self.include_targets.append(entity_id)
        return {"result": "ok", "mode": None}

    def add_pattern(self, raw: str, job: Mapping[str, Any]) -> dict[str, Any]:
        try:
            normalized = normalize_entity_patterns([raw])
        except ValueError:
            return {"result": "invalid", "mode": None}
        if not normalized:
            return {"result": "invalid", "mode": None}
        pattern = normalized[0]
        patterns = self.options[CONF_ENTITY_PATTERNS]
        if pattern in patterns:
            # Schon da (von Hand oder früher): kein Ledger-Eintrag, bleibt „manuell“.
            return {"result": "already", "mode": None}
        if len(patterns) >= MAX_ENTITY_PATTERNS:
            return {"result": "too_many", "mode": None}
        patterns.append(pattern)
        self.ledger.setdefault("patterns", {})[pattern] = {
            "origin": "assistant",
            "topic": job.get("topic"),
            "added_ts": self.now,
            "change_id": job["id"],
        }
        self.added_patterns.append(pattern)
        return {"result": "ok", "mode": None}

    def remove_pattern(self, raw: str) -> dict[str, Any]:
        try:
            normalized = normalize_entity_patterns([raw])
        except ValueError:
            return {"result": "invalid", "mode": None}
        if not normalized:
            return {"result": "invalid", "mode": None}
        pattern = normalized[0]
        patterns = self.options[CONF_ENTITY_PATTERNS]
        ledger_patterns = self.ledger.setdefault("patterns", {})
        if pattern in ledger_patterns:
            del ledger_patterns[pattern]
            if pattern in patterns:
                patterns.remove(pattern)
                return {"result": "ok", "mode": None}
            return {"result": "already", "mode": None}
        if pattern in patterns:
            # Von Hand in HA angelegt: nur dort änderbar.
            return {"result": "unsupported", "mode": None}
        return {"result": "already", "mode": None}

    def apply(self, key: str, job: Mapping[str, Any]) -> dict[str, Any]:
        action = job["action"]
        if action == "add":
            return self.add(key, job)
        if action == "remove":
            return self.remove(key)
        if action == "exclude":
            return self.exclude(key)
        if action == "include":
            return self.include(key)
        if action == "add_patterns":
            return self.add_pattern(key, job)
        return self.remove_pattern(key)


def apply_jobs(
    raw_jobs: list[Any],
    options: Mapping[str, Any],
    ledger: dict[str, Any],
    ports: SelectionPorts,
    now: float,
    *,
    on_error: Callable[[str, BaseException], None] | None = None,
) -> ApplyOutcome:
    """Wendet alle Aufträge eines Abrufs an.

    Bereits angewendete, nur noch nicht quittierte Aufträge (``pending_acks``)
    werden nicht erneut angewendet, ihr Ack wird nur wiederholt. Ein Fehler
    bei einer einzelnen Entität wird deren Ergebnis ``error`` und stört weder
    die anderen Entitäten noch die anderen Aufträge."""
    working = _copy_options(options)
    before = options_snapshot(options)
    run = _Run(ledger, ports, working, now)
    outcome = ApplyOutcome(options=working, options_changed=False)
    pending = ledger.setdefault("pending_acks", {})
    seen: set[str] = set()
    for raw in raw_jobs:
        job, problem = normalize_job(raw, now)
        job_id = raw.get("id") if isinstance(raw, Mapping) else None
        if job is None:
            if problem and is_change_id(job_id) and job_id not in pending and job_id not in seen:
                seen.add(job_id)
                ack = {"job_id": job_id, "status": "failed", "results": {}, "message": problem}
                pending[job_id] = ack
                outcome.acks.append(ack)
            elif is_change_id(job_id):
                outcome.skipped.append(job_id)
            continue
        if job["id"] in pending or job["id"] in seen:
            outcome.skipped.append(job["id"])
            continue
        seen.add(job["id"])
        results: dict[str, dict[str, Any]] = {}
        # Ergebnis-Schlüssel: Entitäts-ID, bei Musteraktionen der Musterstring.
        keys = job["patterns"] if job["action"] in PATTERN_ACTIONS else job["entity_ids"]
        for key in keys:
            try:
                results[key] = run.apply(key, job)
            except Exception as err:  # noqa: BLE001 — eine Entität darf den Rest nicht stören
                results[key] = {"result": "error", "mode": None}
                if on_error is not None:
                    on_error(key, err)
        status = job_status(results)
        entry = make_log_entry(job, results, status, now)
        append_log(ledger, entry)
        outcome.log_entries.append(entry)
        ack = {"job_id": job["id"], "status": status, "results": results, "message": None}
        pending[job["id"]] = ack
        outcome.acks.append(ack)
    # Älteste offene Acks fallen bei Überlauf weg (die App lässt sie verfallen).
    while len(pending) > PENDING_ACKS_LIMIT:
        pending.pop(next(iter(pending)))
    outcome.label_targets = list(dict.fromkeys(run.label_targets))
    outcome.include_targets = list(dict.fromkeys(run.include_targets))
    # Ein später im selben Durchgang wieder entferntes Muster zählt nicht.
    outcome.added_patterns = [p for p in dict.fromkeys(run.added_patterns) if p in working[CONF_ENTITY_PATTERNS]]
    after = options_snapshot(working)
    outcome.options_changed = after != before
    # Eigene Änderung: den erwarteten Snapshot VOR async_update_entry setzen,
    # damit der Abgleich beim Neuladen keinen manual_ha-Eintrag erzeugt.
    ledger["options_snapshot"] = after
    return outcome


def pending_acks(ledger: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Noch nicht quittierte Acks (aus einem früheren, unterbrochenen Durchgang)."""
    return [dict(ack) for ack in (ledger.get("pending_acks") or {}).values()]
