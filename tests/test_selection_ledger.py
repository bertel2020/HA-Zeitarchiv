"""Ledger, Options-Abgleich, Verlauf und Herkunft des Auswahl-Assistenten (ROADMAP 1.33)."""

from __future__ import annotations

import _pkg  # noqa: F401

from custom_components.zeitarchiv.selection_ledger import (
    LOG_IDS_LIMIT,
    LOG_LIMIT,
    append_log,
    compute_origin,
    detect_manual_change,
    diff_options,
    empty_ledger,
    job_status,
    make_log_entry,
    normalize_ledger,
    options_snapshot,
)


def test_normalize_ledger_drops_garbage_and_keeps_valid_parts() -> None:
    raw = {
        "entries": {
            "sensor.ok": {"mode": "label", "topic": "  energie ", "added_ts": 5, "change_id": "abc"},
            "sensor.bad_mode": {"mode": "pattern"},
            "Kein.Eintrag": {"mode": "ids"},
            "sensor.not_a_dict": "x",
        },
        "label_id": "",
        "options_snapshot": {"entities": ["b", "a", "a"], "decimal_places": 2},
        "log": [{"id": "e1"}, "kaputt", {"id": "mit leerzeichen"}],
        "pending_acks": {"j1": {"job_id": "j1"}, "bad id": {}},
    }
    ledger = normalize_ledger(raw)
    assert list(ledger["entries"]) == ["sensor.ok"]
    assert ledger["entries"]["sensor.ok"]["topic"] == "energie"
    assert ledger["entries"]["sensor.ok"]["added_ts"] == 5.0
    assert ledger["label_id"] is None
    assert ledger["options_snapshot"]["entities"] == ["a", "b"]
    assert "decimal_places" not in ledger["options_snapshot"]
    assert [entry["id"] for entry in ledger["log"]] == ["e1"]
    assert list(ledger["pending_acks"]) == ["j1"]
    assert normalize_ledger(None) == empty_ledger()
    assert normalize_ledger("kaputt") == empty_ledger()


def test_options_snapshot_only_filter_keys() -> None:
    snapshot = options_snapshot({"entities": ("sensor.b", "sensor.a"), "labels": "x", "decimal_places": 3, "areas": None})
    assert snapshot["entities"] == ["sensor.a", "sensor.b"]
    assert snapshot["labels"] == ["x"] and snapshot["areas"] == []
    assert "decimal_places" not in snapshot


def test_diff_options_summarises_keys_and_effective_counts() -> None:
    old = {"entities": ["sensor.a", "sensor.b"], "entity_patterns": []}
    new = {"entities": ["sensor.a", "sensor.c"], "entity_patterns": ["*_energy"], "exclude_entities": ["sensor.x"], "decimal_places": 1}
    detail = diff_options(old, new)
    assert detail["kind"] == "options"
    assert detail["added_entities"] == 1 and detail["removed_entities"] == 1
    assert detail["patterns"] == "+1" and detail["excluded"] == "+1" and detail["areas"] == "0"
    assert "entity_patterns +1/-0" in detail["summary"]
    effective = diff_options(old, new, effective_before={"sensor.a", "sensor.b"}, effective_after={"sensor.a", "sensor.c", *(f"sensor.e{i}" for i in range(34))})
    assert effective["added_entities"] == 35 and effective["removed_entities"] == 1
    assert diff_options(old, {**old, "decimal_places": 4}) is None
    assert diff_options({"labels": ["a", "b"]}, {"labels": ["a"]})["labels"] == "-1"


def test_detect_manual_change_first_start_only_creates_snapshot() -> None:
    ledger = empty_ledger()
    assert detect_manual_change(ledger, {"entities": ["sensor.a"]}, 1.0) is None
    assert ledger["options_snapshot"]["entities"] == ["sensor.a"]
    assert ledger["log"] == []


def test_detect_manual_change_logs_one_entry_and_updates_snapshot() -> None:
    ledger = empty_ledger()
    ledger["options_snapshot"] = options_snapshot({"entities": ["sensor.a"]})
    entry = detect_manual_change(ledger, {"entities": ["sensor.a", "sensor.b"], "areas": ["kueche"]}, 2.0)
    assert entry["source"] == "manual_ha" and entry["action"] == "change" and entry["status"] == "applied"
    assert entry["ha_detail"]["added_entities"] == 1 and entry["ha_detail"]["areas"] == "+1"
    assert ledger["log"] == [entry]
    assert ledger["options_snapshot"]["areas"] == ["kueche"]
    # Unverändert beim nächsten Start: kein weiterer Eintrag.
    assert detect_manual_change(ledger, {"entities": ["sensor.b", "sensor.a"], "areas": ["kueche"]}, 3.0) is None
    assert len(ledger["log"]) == 1


def test_job_status() -> None:
    assert job_status({}) == "failed"
    assert job_status({"a": {"result": "ok"}, "b": {"result": "already"}}) == "applied"
    assert job_status({"a": {"result": "ok"}, "b": {"result": "excluded"}}) == "partial"
    assert job_status({"a": {"result": "not_found"}}) == "failed"


def test_log_entry_caps_ids_and_results() -> None:
    ids = [f"sensor.s{i}" for i in range(120)]
    results = {eid: {"result": "ok", "mode": "label"} for eid in ids}
    job = {"id": "job1", "source": "assistant", "action": "add", "mode": "label", "topic": "energie", "entity_ids": ids, "undo_of": None}
    entry = make_log_entry(job, results, "applied", 9.0)
    assert entry["id"] == "job1" and entry["count"] == 120
    assert len(entry["entity_ids"]) == LOG_IDS_LIMIT and len(entry["results"]) == LOG_IDS_LIMIT
    assert entry["undone_by"] is None and entry["ha_detail"] is None
    remove = make_log_entry({**job, "action": "remove", "mode": "auto"}, {"sensor.s0": {"result": "ok", "mode": "ids"}}, "applied", 1.0)
    assert remove["mode"] == "ids"


def test_append_log_newest_first_capped_and_links_undo() -> None:
    ledger = empty_ledger()
    for i in range(LOG_LIMIT + 5):
        append_log(ledger, {"id": f"e{i}", "source": "assistant", "status": "applied"})
    assert len(ledger["log"]) == LOG_LIMIT and ledger["log"][0]["id"] == f"e{LOG_LIMIT + 4}"
    target = ledger["log"][3]["id"]
    append_log(ledger, {"id": "u1", "source": "undo", "status": "applied", "undo_of": target})
    assert next(item for item in ledger["log"] if item["id"] == target)["undone_by"] == "u1"
    # Ein gescheitertes Rückgängig verknüpft nichts; manual_ha ist nie rückgängig machbar.
    append_log(ledger, {"id": "ha1", "source": "manual_ha", "status": "applied"})
    append_log(ledger, {"id": "u2", "source": "undo", "status": "applied", "undo_of": "ha1"})
    append_log(ledger, {"id": "u3", "source": "undo", "status": "failed", "undo_of": ledger["log"][5]["id"]})
    assert next(item for item in ledger["log"] if item["id"] == "ha1").get("undone_by") is None
    assert ledger["log"][5].get("undone_by") is None


ASSISTANT_LABEL = {"mode": "label", "topic": "energie", "added_ts": 1.0}
ASSISTANT_IDS = {"mode": "ids", "topic": "wetter", "added_ts": 2.0}


def test_compute_origin_assistant_manual_none_and_drifted() -> None:
    by_label = {"selected": True, "via": [{"type": "label", "value": "za", "level": "entity"}]}
    assert compute_origin(ASSISTANT_LABEL, by_label, "za") == {"origin": "assistant", "drifted": False, "topic": "energie", "added_ts": 1.0}
    # Label in HA vom Eintrag genommen, Entität aber noch über ein Muster drin.
    by_pattern = {"selected": True, "via": [{"type": "pattern", "value": "*"}]}
    assert compute_origin(ASSISTANT_LABEL, by_pattern, "za")["origin"] == "manual"
    assert compute_origin(ASSISTANT_LABEL, by_pattern, "za")["drifted"] is True
    # Label nur am Gerät zählt nicht als Assistenten-Weg.
    device_label = {"selected": True, "via": [{"type": "label", "value": "za", "level": "device"}]}
    assert compute_origin(ASSISTANT_LABEL, device_label, "za")["drifted"] is True
    by_id = {"selected": True, "via": [{"type": "entity"}]}
    assert compute_origin(ASSISTANT_IDS, by_id, None)["origin"] == "assistant"
    assert compute_origin(None, by_id, None) == {"origin": "manual", "drifted": False, "topic": None, "added_ts": None}
    gone = {"selected": False, "via": []}
    assert compute_origin(ASSISTANT_IDS, gone, None) == {"origin": None, "drifted": True, "topic": "wetter", "added_ts": 2.0}
    excluded = {"selected": False, "via": [{"type": "entity"}], "excluded_by": [{"type": "entity"}]}
    assert compute_origin(ASSISTANT_IDS, excluded, None)["drifted"] is True
    assert compute_origin(None, gone, None)["origin"] is None
