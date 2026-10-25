"""Auswahl-Assistent Phase 2 in der Integration (ROADMAP 1.33): Ausschließen /
Wieder aufnehmen, Muster, Katalog-Muster, Registry-Ereignisse."""

from __future__ import annotations

from types import SimpleNamespace

import _pkg  # noqa: F401
from test_catalog import LabeledEntry, Registry
from test_selection_apply import NOW, FakePorts, job

from custom_components.zeitarchiv.catalog import build_catalog, build_catalog_body, catalog_patterns
from custom_components.zeitarchiv.registry_events import (
    EVENT_AREA,
    EVENT_DEVICE,
    EVENT_ENTITY,
    EVENT_LABEL,
    RegistryChange,
    classify_registry_event,
    newly_selected,
)
from custom_components.zeitarchiv.registry_filter import ArchiveFilterMatcher
from custom_components.zeitarchiv.selection_apply import apply_jobs, normalize_job, pattern_targets
from custom_components.zeitarchiv.selection_ledger import (
    assistant_label_removed,
    empty_ledger,
    make_label_drift_entry,
    normalize_ledger,
)


def pjob(job_id: str = "p1", **kw):
    return job(job_id, **{"action": "add_patterns", "mode": "ids", "entity_ids": [], **kw})


# ------------------------------------------------------------------ Aufträge prüfen


def test_normalize_job_phase2_fields() -> None:
    good, problem = normalize_job(pjob(patterns=["*_energy", "*_energy", "sensor.pv_*"]), NOW)
    assert problem is None and good["patterns"] == ["*_energy", "sensor.pv_*"] and good["entity_ids"] == []
    assert good["mode"] == "ids"
    assert normalize_job(pjob(action="remove_patterns", mode="label", patterns=["x_*"]), NOW)[0]["mode"] == "auto"
    assert normalize_job(job(action="exclude", mode="label", entity_ids=["sensor.a"]), NOW)[0]["mode"] == "auto"
    assert normalize_job(job(action="include", entity_ids=["sensor.a"]), NOW)[0]["mode"] == "auto"
    for bad in ([], None, ["ok_*", 5], [" "], ["x" * 129], [f"p{i}_*" for i in range(21)]):
        assert normalize_job(pjob(patterns=bad), NOW) == (None, "invalid_patterns")
    # Ausschließen braucht weiter Entitäts-IDs.
    assert normalize_job(job(action="exclude", entity_ids=[]), NOW) == (None, "invalid_entity_ids")
    # unexclude_ids nur bei add und nur als Teilmenge.
    added = normalize_job(job(entity_ids=["sensor.a", "sensor.b"], unexclude_ids=["sensor.b", "sensor.x"]), NOW)[0]
    assert added["unexclude_ids"] == ["sensor.b"]
    removed = normalize_job(job(action="remove", entity_ids=["sensor.a"], unexclude_ids=["sensor.a"]), NOW)[0]
    assert removed["unexclude_ids"] == []
    # Ohne die neuen Felder (Phase-1-Auftrag) bleibt alles wie bisher.
    old = normalize_job(job(entity_ids=["sensor.a"]), NOW)[0]
    assert old["unexclude_ids"] == [] and old["patterns"] == []


# ------------------------------------------------------------------ Ausschließen / Wieder aufnehmen


def test_exclude_ok_already_not_found_and_ledger_untouched() -> None:
    ports = FakePorts({"sensor.a": {"lbl_za"}}, {})
    ledger = {**empty_ledger(), "label_id": "lbl_za", "entries": {
        "sensor.a": {"origin": "assistant", "mode": "label", "topic": None, "added_ts": 1.0, "change_id": "a"}}}
    outcome = apply_jobs(
        [job(action="exclude", source="manual_ui", entity_ids=["sensor.a", "sensor.nie_gesehen", "sensor.schon", "Kaputt"])],
        {"exclude_entities": ["sensor.schon"], "labels": ["lbl_za"]}, ledger, ports, NOW,
    )
    results = outcome.acks[0]["results"]
    assert results["sensor.a"] == {"result": "ok", "mode": None}
    assert results["sensor.nie_gesehen"]["result"] == "ok"  # auch unbekannte IDs
    assert results["sensor.schon"]["result"] == "already"
    assert results["Kaputt"]["result"] == "not_found"
    assert outcome.options["exclude_entities"] == ["sensor.schon", "sensor.a", "sensor.nie_gesehen"]
    assert outcome.options_changed is True
    assert "sensor.a" in ledger["entries"] and ports.registry["sensor.a"] == {"lbl_za"}
    assert ledger["log"][0]["action"] == "exclude" and outcome.acks[0]["status"] == "partial"


def test_include_removes_entity_exclusion_but_pattern_blocks() -> None:
    ports = FakePorts({"sensor.a": set()}, {})
    options = {
        "entities": ["sensor.a", "sensor.p_x"],
        "exclude_entities": ["sensor.a", "sensor.p_x", "sensor.frei"],
        "exclude_entity_patterns": ["p_*"],
    }
    outcome = apply_jobs(
        [job(action="include", source="manual_ui", entity_ids=["sensor.a", "sensor.p_x", "sensor.frei", "sensor.nie"])],
        options, empty_ledger(), ports, NOW,
    )
    results = outcome.acks[0]["results"]
    assert results["sensor.a"]["result"] == "ok"
    assert results["sensor.p_x"]["result"] == "blocked"
    assert results["sensor.frei"]["result"] == "ok"
    assert results["sensor.nie"]["result"] == "already"
    assert outcome.options["exclude_entities"] == ["sensor.p_x"]
    # Nachsenden nur, wenn die Entität jetzt tatsächlich erfasst ist.
    assert outcome.include_targets == ["sensor.a"]


def test_exclude_and_include_undo_links() -> None:
    ports = FakePorts({"sensor.a": set()}, {})
    ledger = empty_ledger()
    first = apply_jobs([job("ex1", action="exclude", entity_ids=["sensor.a"])], {}, ledger, ports, NOW)
    ledger["pending_acks"].clear()
    apply_jobs(
        [job("un1", source="undo", action="include", entity_ids=["sensor.a"], undo_of="ex1")],
        first.options, ledger, ports, NOW + 1,
    )
    assert next(item for item in ledger["log"] if item["id"] == "ex1")["undone_by"] == "un1"


def test_add_with_unexclude_ids() -> None:
    ports = FakePorts({"sensor.a": set(), "sensor.b": set(), "sensor.m_x": set()}, {})
    options = {"exclude_entities": ["sensor.a", "sensor.b", "sensor.m_x"], "exclude_entity_patterns": ["m_*"]}
    outcome = apply_jobs(
        [job(mode="ids", entity_ids=["sensor.a", "sensor.b", "sensor.m_x"], unexclude_ids=["sensor.a", "sensor.m_x"])],
        options, empty_ledger(), ports, NOW,
    )
    results = outcome.acks[0]["results"]
    assert results["sensor.a"] == {"result": "ok", "mode": "ids"}
    assert results["sensor.b"]["result"] == "excluded"  # nicht ausdrücklich freigegeben
    assert results["sensor.m_x"]["result"] == "excluded"  # Muster-Ausschluss bleibt
    assert outcome.options["exclude_entities"] == ["sensor.b", "sensor.m_x"]
    assert outcome.options["entities"] == ["sensor.a"]


def test_unexclude_when_another_way_already_selects() -> None:
    ports = FakePorts({"sensor.pv_a": set()}, {})
    options = {"entity_patterns": ["pv_*"], "exclude_entities": ["sensor.pv_a"]}
    outcome = apply_jobs(
        [job(mode="ids", entity_ids=["sensor.pv_a"], unexclude_ids=["sensor.pv_a"])], options, empty_ledger(), ports, NOW,
    )
    assert outcome.acks[0]["results"]["sensor.pv_a"] == {"result": "ok", "mode": None}
    assert outcome.options["exclude_entities"] == [] and outcome.options["entities"] == []


# ------------------------------------------------------------------ Muster


def test_add_patterns_results_ledger_and_log() -> None:
    ports = FakePorts({}, {})
    ledger = empty_ledger()
    options = {"entity_patterns": ["hand_*"]}
    outcome = apply_jobs(
        [pjob(patterns=["*_Energy", "hand_*", "kaputt[", "sensor.pv_*"])], options, ledger, ports, NOW,
    )
    results = outcome.acks[0]["results"]
    # Schlüssel ist der gesendete Musterstring.
    assert results == {
        "*_Energy": {"result": "ok", "mode": None},
        "hand_*": {"result": "already", "mode": None},
        "kaputt[": {"result": "invalid", "mode": None},
        "sensor.pv_*": {"result": "ok", "mode": None},
    }
    assert outcome.options["entity_patterns"] == ["hand_*", "*_energy", "sensor.pv_*"]
    assert set(ledger["patterns"]) == {"*_energy", "sensor.pv_*"}  # schon vorhandenes bleibt „manuell“
    assert ledger["patterns"]["*_energy"] == {"origin": "assistant", "topic": "energie", "added_ts": NOW, "change_id": "p1"}
    assert outcome.added_patterns == ["*_energy", "sensor.pv_*"]
    entry = ledger["log"][0]
    assert entry["action"] == "add_patterns" and entry["entity_ids"] == [] and entry["count"] == 4
    assert entry["patterns"] == ["*_Energy", "hand_*", "kaputt[", "sensor.pv_*"]
    assert entry["results"]["kaputt["]["result"] == "invalid"
    assert entry["mode"] == "ids" and entry["status"] == "partial"


def test_add_patterns_limit() -> None:
    options = {"entity_patterns": [f"p{i}_*" for i in range(99)]}
    outcome = apply_jobs([pjob(patterns=["neu_*", "noch_*"])], options, empty_ledger(), FakePorts({}), NOW)
    assert outcome.acks[0]["results"]["neu_*"]["result"] == "ok"
    assert outcome.acks[0]["results"]["noch_*"]["result"] == "too_many"
    assert len(outcome.options["entity_patterns"]) == 100


def test_remove_patterns_only_assistant_patterns() -> None:
    ledger = {**empty_ledger(), "patterns": {
        "pv_*": {"origin": "assistant", "topic": "energie", "added_ts": 1.0, "change_id": "p0"},
        "weg_*": {"origin": "assistant", "topic": None, "added_ts": 1.0, "change_id": "p0"},
    }}
    options = {"entity_patterns": ["pv_*", "hand_*"]}
    outcome = apply_jobs(
        [pjob(action="remove_patterns", source="manual_ui", patterns=["pv_*", "hand_*", "nie_*", "weg_*"])],
        options, ledger, FakePorts({}), NOW,
    )
    results = outcome.acks[0]["results"]
    assert results["pv_*"]["result"] == "ok"
    assert results["hand_*"]["result"] == "unsupported"
    assert results["nie_*"]["result"] == "already"
    assert results["weg_*"]["result"] == "already"  # nur noch im Ledger: aufgeräumt
    assert outcome.options["entity_patterns"] == ["hand_*"]
    assert ledger["patterns"] == {}
    assert ledger["log"][0]["action"] == "remove_patterns"


def test_pattern_added_and_removed_in_one_run_is_not_a_target() -> None:
    outcome = apply_jobs(
        [pjob(patterns=["pv_*"]), pjob("p2", action="remove_patterns", patterns=["pv_*"])],
        {}, empty_ledger(), FakePorts({}), NOW,
    )
    assert outcome.added_patterns == [] and outcome.options_changed is False


def test_pattern_targets_skip_text_excluded_and_already_selected() -> None:
    options = {"entity_patterns": ["pv_*"], "exclude_entities": ["sensor.pv_privat"], "entities": ["sensor.pv_alt"]}
    targets = pattern_targets(
        ["sensor.pv_neu", "sensor.pv_text", "sensor.pv_privat", "sensor.pv_alt", "sensor.wetter", "sensor.pv_neu"],
        ["pv_*"], options,
        is_text=lambda eid: eid == "sensor.pv_text",
        was_selected=lambda eid: eid == "sensor.pv_alt",
    )
    assert targets == ["sensor.pv_neu"]
    assert pattern_targets(["sensor.pv_neu"], [], options, is_text=lambda _: False, was_selected=lambda _: False) == []


# ------------------------------------------------------------------ Ledger


def test_ledger_backward_compatible_and_patterns_cleaned() -> None:
    old_store = {"entries": {}, "label_id": "l", "options_snapshot": None, "log": []}
    assert normalize_ledger(old_store)["patterns"] == {}
    ledger = normalize_ledger({"patterns": {
        "pv_*": {"topic": " energie ", "added_ts": 3, "change_id": "abc"},
        "Groß*": {"topic": None},
        "x_*": "kaputt",
        "a" * 200: {},
    }})
    assert ledger["patterns"] == {"pv_*": {"origin": "assistant", "topic": "energie", "added_ts": 3.0, "change_id": "abc"}}
    assert empty_ledger()["patterns"] == {}


def test_assistant_label_removed_and_drift_entry() -> None:
    ledger = {**empty_ledger(), "label_id": "za", "entries": {
        "sensor.a": {"mode": "label"}, "sensor.ids": {"mode": "ids"}}}
    assert assistant_label_removed("sensor.a", {"za", "x"}, {"x"}, ledger, ["za"]) is True
    assert assistant_label_removed("sensor.a", {"x"}, set(), ledger, ["za"]) is False  # hatte es nicht
    assert assistant_label_removed("sensor.a", {"za"}, {"za"}, ledger, ["za"]) is False
    assert assistant_label_removed("sensor.ids", {"za"}, set(), ledger, ["za"]) is False
    assert assistant_label_removed("sensor.weg", {"za"}, set(), ledger, ["za"]) is False  # eigenes remove: Eintrag schon weg
    assert assistant_label_removed("sensor.a", {"za"}, set(), ledger, []) is False  # schon vom Options-Abgleich erfasst
    entry = make_label_drift_entry({"sensor.b", "sensor.a"}, 5.0)
    assert entry["source"] == "manual_ha" and entry["action"] == "change"
    assert entry["entity_ids"] == ["sensor.a", "sensor.b"] and entry["count"] == 2
    assert entry["ha_detail"]["kind"] == "options" and entry["ha_detail"]["removed_entities"] == 2


# ------------------------------------------------------------------ Katalog


def test_catalog_patterns_and_assistant_flag_in_via() -> None:
    entity_registry = Registry({eid: LabeledEntry() for eid in ("sensor.pv_a", "sensor.pv_b", "sensor.pv_text", "sensor.temp")})
    options = {"entity_patterns": ["pv_*", "temp", "leer_*"]}
    matcher = ArchiveFilterMatcher(options, entity_registry, Registry({}), Registry({}))
    states = [
        SimpleNamespace(entity_id="sensor.pv_a", state="1", attributes={}),
        SimpleNamespace(entity_id="sensor.pv_b", state="2", attributes={}),
        SimpleNamespace(entity_id="sensor.pv_text", state="an", attributes={}),
        SimpleNamespace(entity_id="sensor.temp", state="20", attributes={}),
    ]
    ledger = {**empty_ledger(), "patterns": {"pv_*": {"origin": "assistant", "topic": "energie", "added_ts": 7.0, "change_id": "p1"}}}
    rows = build_catalog(states, entity_registry, Registry({}), Registry({}), matcher, ledger=ledger)
    by_id = {row["entity_id"]: row for row in rows}
    assert by_id["sensor.pv_a"]["via"] == [{"type": "pattern", "value": "pv_*", "assistant": True}]
    assert by_id["sensor.temp"]["via"] == [{"type": "pattern", "value": "temp"}]
    body = build_catalog_body(rows, ledger, None, options)
    assert body["patterns"] == [
        {"pattern": "pv_*", "origin": "assistant", "topic": "energie", "added_ts": 7.0, "count": 2},
        {"pattern": "temp", "origin": "manual", "topic": None, "added_ts": None, "count": 1},
        {"pattern": "leer_*", "origin": "manual", "topic": None, "added_ts": None, "count": 0},
    ]
    assert build_catalog_body(rows, ledger)["patterns"] == []
    assert len(catalog_patterns([], {"entity_patterns": [f"p{i}" for i in range(150)]}, None)) == 100


# ------------------------------------------------------------------ Registry-Ereignisse


def test_classify_registry_event() -> None:
    update = {"action": "update", "entity_id": "sensor.a"}
    assert classify_registry_event(EVENT_ENTITY, {**update, "changes": {"labels": {"x"}}}) == RegistryChange(
        entity_id="sensor.a", old_labels=frozenset({"x"}))
    assert classify_registry_event(EVENT_ENTITY, {**update, "changes": {"area_id": None}}).entity_id == "sensor.a"
    assert classify_registry_event(EVENT_ENTITY, {**update, "changes": {"name": "neu"}}) is None
    assert classify_registry_event(EVENT_ENTITY, {"action": "create", "entity_id": "sensor.b"}).entity_id == "sensor.b"
    assert classify_registry_event(EVENT_ENTITY, {"action": "update"}) is None
    assert classify_registry_event(EVENT_DEVICE, {"action": "update", "device_id": "d", "changes": {"labels": set()}}).device_id == "d"
    assert classify_registry_event(EVENT_DEVICE, {"action": "update", "device_id": "d", "changes": {"name": "x"}}) is None
    assert classify_registry_event(EVENT_DEVICE, {"action": "create", "device_id": "d"}) is None
    assert classify_registry_event(EVENT_AREA, {"action": "update", "area_id": "k"}).wide is True
    assert classify_registry_event(EVENT_AREA, {"action": "create", "area_id": "k"}) is None
    assert classify_registry_event(EVENT_LABEL, {"action": "update", "label_id": "x"}, selected_labels={"x"}).wide is True
    assert classify_registry_event(EVENT_LABEL, {"action": "remove", "label_id": "za"}, managed_label_id="za").wide is True
    assert classify_registry_event(EVENT_LABEL, {"action": "update", "label_id": "fremd"}, selected_labels={"x"}) is None
    assert classify_registry_event("state_changed", {"action": "update"}) is None
    assert classify_registry_event(EVENT_ENTITY, None) is None


def test_newly_selected_from_before_and_after() -> None:
    before = {"sensor.a", "sensor.b"}
    after = {"sensor.a", "sensor.c", "sensor.d"}
    assert newly_selected(before, after) == ["sensor.c", "sensor.d"]
    assert newly_selected(before, after, {"sensor.c", "sensor.b"}) == ["sensor.c"]
    assert newly_selected(after, before) == ["sensor.b"]
    assert newly_selected(before, before) == []
