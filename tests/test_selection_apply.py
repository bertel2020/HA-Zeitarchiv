"""Anwendung von Auswahl-Aufträgen auf Optionen und Registry (ROADMAP 1.33)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import _pkg  # noqa: F401

from custom_components.zeitarchiv.filtering import should_archive
from custom_components.zeitarchiv.selection_apply import apply_jobs, normalize_job, pending_acks
from custom_components.zeitarchiv.selection_ledger import empty_ledger, options_snapshot

NOW = 1000.0


class FakePorts:
    """Registry-Einträge mit Labels, States mit Text-Flag; Auswahl wie der echte Matcher (nur Entity-Labels)."""

    def __init__(self, registry: dict[str, set[str]], states: dict[str, bool] | None = None) -> None:
        self.registry = registry
        self.states = states or {}
        self.labels_created: list[str] = []
        self.label_exists: set[str] = set()
        self.fail_on: set[str] = set()
        self.label_writes: list[tuple[str, set[str]]] = []

    def known(self, entity_id: str) -> bool:
        return entity_id in self.registry or entity_id in self.states

    def has_registry_entry(self, entity_id: str) -> bool:
        return entity_id in self.registry

    def is_text(self, entity_id: str) -> bool:
        return self.states.get(entity_id, False)

    def entity_labels(self, entity_id: str) -> set[str]:
        return set(self.registry.get(entity_id, set()))

    def set_entity_labels(self, entity_id: str, labels: set[str]) -> None:
        if entity_id in self.fail_on:
            raise RuntimeError("registry kaputt")
        self.registry[entity_id] = set(labels)
        self.label_writes.append((entity_id, set(labels)))

    def ensure_label(self, known_label_id: str | None) -> str:
        if known_label_id and known_label_id in self.label_exists:
            return known_label_id
        self.labels_created.append("lbl_new")
        self.label_exists.add("lbl_new")
        return "lbl_new"

    def is_selected(self, entity_id: str, options: Mapping[str, Any]) -> bool:
        return should_archive(
            entity_id,
            set(options.get("entities") or ()),
            set(options.get("exclude_entities") or ()),
            list(options.get("entity_patterns") or ()),
            list(options.get("exclude_entity_patterns") or ()),
            included_by_registry=bool(set(options.get("labels") or ()) & self.registry.get(entity_id, set())),
        )


def job(job_id: str = "j1", **kw: Any) -> dict[str, Any]:
    base = {
        "id": job_id, "created_ts": NOW - 10, "expires_ts": NOW + 86400, "source": "assistant",
        "action": "add", "mode": "label", "topic": "energie", "entity_ids": [], "undo_of": None, "force_ids": [],
    }
    base.update(kw)
    return base


def test_normalize_job_rules() -> None:
    good, problem = normalize_job(job(entity_ids=["sensor.a", "sensor.a", 5, "sensor.b"], force_ids=["sensor.b", "sensor.x"]), NOW)
    assert problem is None
    assert good["entity_ids"] == ["sensor.a", "sensor.b"] and good["force_ids"] == ["sensor.b"]
    assert normalize_job(job(expires_ts=NOW - 1, entity_ids=["sensor.a"]), NOW) == (None, None)
    assert normalize_job({"id": "kein gültiger"}, NOW) == (None, None)
    assert normalize_job(job(action="delete", entity_ids=["sensor.a"]), NOW) == (None, "invalid_action")
    assert normalize_job(job(source="manual_ha", entity_ids=["sensor.a"]), NOW) == (None, "invalid_source")
    assert normalize_job(job(mode="auto", entity_ids=["sensor.a"]), NOW) == (None, "invalid_mode")
    assert normalize_job(job(entity_ids=[]), NOW) == (None, "invalid_entity_ids")
    assert normalize_job(job(entity_ids=[f"sensor.s{i}" for i in range(201)]), NOW) == (None, "invalid_entity_ids")
    assert normalize_job(job(action="remove", mode="label", entity_ids=["sensor.a"]), NOW)[0]["mode"] == "auto"


def test_add_label_mode_creates_label_sets_it_and_adds_option() -> None:
    ports = FakePorts({"sensor.a": set(), "sensor.b": {"fremd"}}, {"sensor.a": False, "sensor.b": False})
    ledger = empty_ledger()
    outcome = apply_jobs([job(entity_ids=["sensor.a", "sensor.b"])], {"entities": []}, ledger, ports, NOW)
    assert ports.registry == {"sensor.a": {"lbl_new"}, "sensor.b": {"fremd", "lbl_new"}}
    assert ports.labels_created == ["lbl_new"]  # einmal je Durchgang
    assert ledger["label_id"] == "lbl_new"
    assert outcome.options["labels"] == ["lbl_new"] and outcome.options_changed is True
    assert outcome.label_targets == ["sensor.a", "sensor.b"]
    assert outcome.acks == [{"job_id": "j1", "status": "applied", "message": None, "results": {
        "sensor.a": {"result": "ok", "mode": "label"}, "sensor.b": {"result": "ok", "mode": "label"}}}]
    assert ledger["entries"]["sensor.a"] == {"origin": "assistant", "mode": "label", "topic": "energie", "added_ts": NOW, "change_id": "j1"}
    assert ledger["log"][0]["id"] == "j1" and ledger["log"][0]["status"] == "applied"
    # Erwarteter Snapshot vor dem Options-Update gesetzt: der nächste Abgleich findet nichts.
    assert ledger["options_snapshot"] == options_snapshot(outcome.options)
    assert "j1" in ledger["pending_acks"]


def test_label_already_in_options_needs_no_option_change() -> None:
    ports = FakePorts({"sensor.a": set()}, {"sensor.a": False})
    ports.label_exists.add("lbl_za")
    ledger = {**empty_ledger(), "label_id": "lbl_za"}
    outcome = apply_jobs([job(entity_ids=["sensor.a"])], {"labels": ["lbl_za"]}, ledger, ports, NOW)
    assert outcome.options_changed is False and ports.labels_created == []
    assert ports.registry["sensor.a"] == {"lbl_za"}


def test_text_force_ids_and_missing_registry_entry_go_as_single_ids() -> None:
    ports = FakePorts(
        {"sensor.text": set(), "sensor.forced": set()},
        {"sensor.text": True, "sensor.forced": False, "sensor.no_registry": False},
    )
    ledger = empty_ledger()
    outcome = apply_jobs(
        [job(entity_ids=["sensor.text", "sensor.forced", "sensor.no_registry"], force_ids=["sensor.forced"])],
        {"entities": ["sensor.old"]}, ledger, ports, NOW,
    )
    assert outcome.options["entities"] == ["sensor.old", "sensor.text", "sensor.forced", "sensor.no_registry"]
    assert {r["mode"] for r in outcome.acks[0]["results"].values()} == {"ids"}
    assert ports.labels_created == [] and outcome.label_targets == []
    assert outcome.options.get("labels") == []


def test_ids_mode_dedupes_and_reports_already() -> None:
    ports = FakePorts({"sensor.a": set(), "sensor.b": set()}, {})
    outcome = apply_jobs(
        [job(mode="ids", entity_ids=["sensor.a", "sensor.b"]), job("j2", mode="ids", entity_ids=["sensor.a"])],
        {"entities": ["sensor.b"]}, empty_ledger(), ports, NOW,
    )
    assert outcome.options["entities"] == ["sensor.b", "sensor.a"]
    assert outcome.acks[0]["results"]["sensor.b"] == {"result": "already", "mode": None}
    assert outcome.acks[0]["status"] == "applied"
    assert outcome.acks[1]["results"]["sensor.a"] == {"result": "already", "mode": "ids"}


def test_excluded_not_found_blocked_and_error_results() -> None:
    ports = FakePorts({"sensor.privat": set(), "sensor.muster_x": set(), "camera.tuer": set(), "sensor.kaputt": set()}, {})
    ports.fail_on.add("sensor.kaputt")
    errors: list[str] = []
    outcome = apply_jobs(
        [job(entity_ids=["sensor.privat", "sensor.muster_x", "sensor.gibts_nicht", "Ungueltig", "camera.tuer", "sensor.kaputt"])],
        {"exclude_entities": ["sensor.privat"], "exclude_entity_patterns": ["muster_*"]},
        empty_ledger(), ports, NOW, on_error=lambda eid, err: errors.append(eid),
    )
    results = outcome.acks[0]["results"]
    assert results["sensor.privat"]["result"] == "excluded"
    assert results["sensor.muster_x"]["result"] == "excluded"
    assert results["sensor.gibts_nicht"]["result"] == "not_found"
    assert results["Ungueltig"]["result"] == "not_found"
    assert results["camera.tuer"]["result"] == "blocked"
    assert results["sensor.kaputt"] == {"result": "error", "mode": None}
    assert errors == ["sensor.kaputt"]
    assert outcome.acks[0]["status"] == "failed"
    assert ports.registry["sensor.privat"] == set()


def test_partial_status_and_bundled_options() -> None:
    ports = FakePorts({"sensor.a": set()}, {"sensor.t": True})
    outcome = apply_jobs(
        [job(entity_ids=["sensor.a", "sensor.nope"]), job("j2", entity_ids=["sensor.t"])],
        {}, empty_ledger(), ports, NOW,
    )
    assert [ack["status"] for ack in outcome.acks] == ["partial", "applied"]
    # Beide Aufträge landen in EINER Arbeitskopie.
    assert outcome.options["labels"] == ["lbl_new"] and outcome.options["entities"] == ["sensor.t"]


def test_remove_by_ledger_mode_manual_id_unsupported_and_already() -> None:
    ports = FakePorts({"sensor.lab": {"lbl_za", "fremd"}, "sensor.muster": set(), "sensor.fremd": {"fremd"}}, {})
    ports.label_exists.add("lbl_za")
    ledger = {**empty_ledger(), "label_id": "lbl_za", "entries": {
        "sensor.lab": {"origin": "assistant", "mode": "label", "topic": "energie", "added_ts": 1.0, "change_id": "a"},
        "sensor.ids": {"origin": "assistant", "mode": "ids", "topic": None, "added_ts": 1.0, "change_id": "a"},
    }}
    options = {"entities": ["sensor.ids", "sensor.hand"], "labels": ["lbl_za", "fremd"], "entity_patterns": ["muster"]}
    outcome = apply_jobs(
        [job(action="remove", mode="auto", source="manual_ui", entity_ids=[
            "sensor.lab", "sensor.ids", "sensor.hand", "sensor.muster", "sensor.fremd", "sensor.weg"])],
        options, ledger, ports, NOW,
    )
    results = outcome.acks[0]["results"]
    assert results["sensor.lab"] == {"result": "ok", "mode": "label"}
    assert ports.registry["sensor.lab"] == {"fremd"}
    assert results["sensor.ids"] == {"result": "ok", "mode": "ids"}
    assert results["sensor.hand"] == {"result": "ok", "mode": "ids"}
    assert outcome.options["entities"] == []
    assert results["sensor.muster"]["result"] == "unsupported"
    assert results["sensor.fremd"]["result"] == "unsupported"
    assert results["sensor.weg"]["result"] == "already"
    assert ledger["entries"] == {}
    assert outcome.acks[0]["status"] == "partial"
    assert ledger["log"][0]["action"] == "remove"


def test_remove_drifted_ledger_entry_cleans_up() -> None:
    ports = FakePorts({"sensor.lab": set()}, {})
    ledger = {**empty_ledger(), "label_id": "lbl_za", "entries": {
        "sensor.lab": {"origin": "assistant", "mode": "label", "topic": None, "added_ts": 1.0, "change_id": "a"}}}
    outcome = apply_jobs([job(action="remove", entity_ids=["sensor.lab"])], {}, ledger, ports, NOW)
    assert outcome.acks[0]["results"]["sensor.lab"]["result"] == "ok"
    assert ledger["entries"] == {} and ports.label_writes == []


def test_managed_label_set_by_hand_is_removable() -> None:
    ports = FakePorts({"sensor.x": {"lbl_za"}}, {})
    ledger = {**empty_ledger(), "label_id": "lbl_za"}
    outcome = apply_jobs([job(action="remove", entity_ids=["sensor.x"])], {"labels": ["lbl_za"]}, ledger, ports, NOW)
    assert outcome.acks[0]["results"]["sensor.x"] == {"result": "ok", "mode": "label"}
    assert ports.registry["sensor.x"] == set()


def test_undo_links_log_entries() -> None:
    ports = FakePorts({"sensor.a": set()}, {})
    ledger = empty_ledger()
    apply_jobs([job("orig", mode="ids", entity_ids=["sensor.a"])], {}, ledger, ports, NOW)
    ledger["pending_acks"].clear()
    outcome = apply_jobs(
        [job("undo1", source="undo", action="remove", entity_ids=["sensor.a"], undo_of="orig")],
        {"entities": ["sensor.a"]}, ledger, ports, NOW + 1,
    )
    assert outcome.options["entities"] == []
    orig = next(entry for entry in ledger["log"] if entry["id"] == "orig")
    assert orig["undone_by"] == "undo1"
    assert ledger["log"][0]["undo_of"] == "orig" and ledger["log"][0]["source"] == "undo"


def test_pending_acks_are_not_applied_twice_and_invalid_jobs_are_failed() -> None:
    ports = FakePorts({"sensor.a": set()}, {})
    ledger = empty_ledger()
    apply_jobs([job(mode="ids", entity_ids=["sensor.a"])], {}, ledger, ports, NOW)
    # Ack ging verloren: die App liefert den Auftrag erneut.
    again = apply_jobs([job(mode="ids", entity_ids=["sensor.a"]), job("bad", action="x", entity_ids=["sensor.a"])], {"entities": ["sensor.a"]}, ledger, ports, NOW)
    assert again.skipped == ["j1"]
    assert again.acks == [{"job_id": "bad", "status": "failed", "results": {}, "message": "invalid_action"}]
    assert len([entry for entry in ledger["log"] if entry["id"] == "j1"]) == 1
    assert {ack["job_id"] for ack in pending_acks(ledger)} == {"j1", "bad"}


def test_no_jobs_leaves_options_unchanged() -> None:
    ledger = empty_ledger()
    outcome = apply_jobs([], {"entities": ["sensor.a"]}, ledger, FakePorts({}), NOW)
    assert outcome.options_changed is False and outcome.acks == []
