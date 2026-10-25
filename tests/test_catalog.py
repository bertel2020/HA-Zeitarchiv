"""Entitäten-Katalog der Integration (ROADMAP 1.33): Energie-Rollen und Aufbereitung."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import _pkg  # noqa: F401

from custom_components.zeitarchiv.catalog import (
    build_catalog,
    catalog_digest,
    energy_roles_from_prefs,
)

PREFS = {
    "energy_sources": [
        {
            "type": "grid",
            "flow_from": [{"stat_energy_from": "sensor.netz_bezug", "stat_rate": "sensor.netz_leistung"}],
            "flow_to": [{"stat_energy_to": "sensor.netz_einspeisung"}],
        },
        {"type": "solar", "stat_energy_from": "sensor.pv_ertrag"},
        {"type": "battery", "stat_energy_from": "sensor.batt_aus", "stat_energy_to": "sensor.batt_ein"},
        {"type": "gas", "stat_energy_from": "sensor.gas_zaehler"},
        {"type": "grid", "flow_from": [{"stat_energy_from": "mein_import:strom"}]},
    ],
    "device_consumption": [{"stat_consumption": "sensor.waermepumpe_energie"}],
    "device_consumption_water": [{"stat_consumption": "sensor.dusche_wasser"}],
}


def test_energy_roles_from_prefs_maps_every_source_kind() -> None:
    roles = energy_roles_from_prefs(PREFS)
    assert roles["sensor.netz_bezug"] == "grid_import"
    assert roles["sensor.netz_leistung"] == "grid_power"
    assert roles["sensor.netz_einspeisung"] == "grid_export"
    assert roles["sensor.pv_ertrag"] == "solar"
    assert roles["sensor.batt_aus"] == "battery_out"
    assert roles["sensor.batt_ein"] == "battery_in"
    assert roles["sensor.gas_zaehler"] == "gas"
    assert roles["sensor.waermepumpe_energie"] == "consumer"
    assert roles["sensor.dusche_wasser"] == "water_consumer"


def test_energy_roles_skip_external_statistics_and_survive_garbage() -> None:
    assert "mein_import:strom" not in energy_roles_from_prefs(PREFS)
    assert energy_roles_from_prefs(None) == {}
    assert energy_roles_from_prefs({"energy_sources": ["kaputt", {"type": "grid", "flow_from": None}]}) == {}


@dataclass
class Entry:
    platform: str = "shelly"
    device_id: str | None = None
    area_id: str | None = None
    name: str | None = None
    original_name: str | None = None
    device_class: str | None = None
    original_device_class: str | None = None
    entity_category: str | None = None
    hidden_by: str | None = None


@dataclass
class Registry:
    entries: dict = field(default_factory=dict)

    def async_get(self, key):
        return self.entries.get(key)

    def async_get_area(self, key):
        return self.entries.get(key)


class Matcher:
    def __init__(self, selected: set[str], excluded: set[str]) -> None:
        self.selected, self.excluded = selected, excluded

    def matches(self, entity_id: str, *, apply_exclusions: bool = True) -> bool:
        if apply_exclusions and entity_id in self.excluded:
            return False
        return entity_id in self.selected | self.excluded


def _state(entity_id: str, **attrs):
    return SimpleNamespace(entity_id=entity_id, attributes=attrs)


def _catalog():
    entity_registry = Registry({
        "sensor.netz_bezug": Entry(device_id="dev1", original_device_class="energy", hidden_by="integration"),
        "sensor.kueche_leistung": Entry(device_id="dev1"),
    })
    device_registry = Registry({"dev1": SimpleNamespace(name="Shelly 3EM", name_by_user=None, area_id="a1")})
    area_registry = Registry({"a1": SimpleNamespace(name="Keller")})
    states = [
        _state("sensor.netz_bezug", friendly_name="Netzbezug", device_class="energy", state_class="total_increasing", unit_of_measurement="kWh"),
        _state("sensor.kueche_leistung", friendly_name="Küche Leistung", device_class="power", unit_of_measurement="W"),
        _state("camera.eingang"),
        _state("sensor.ignoriert"),
    ]
    return build_catalog(
        states, entity_registry, device_registry, area_registry,
        Matcher({"sensor.netz_bezug"}, {"sensor.ignoriert"}),
        {"sensor.netz_bezug": "grid_import"},
    )


def test_build_catalog_collects_metadata_without_values() -> None:
    rows = {row["entity_id"]: row for row in _catalog()}
    assert "camera.eingang" not in rows
    netz = rows["sensor.netz_bezug"]
    assert netz["name"] == "Netzbezug"
    assert netz["device_class"] == "energy" and netz["state_class"] == "total_increasing"
    assert netz["unit"] == "kWh" and netz["platform"] == "shelly"
    assert netz["device"] == "Shelly 3EM" and netz["area"] == "Keller"
    assert netz["hidden"] is True and netz["energy_role"] == "grid_import"
    assert netz["selected"] is True and netz["excluded"] is False
    assert not any("state" == key or key == "value" for key in netz)


def test_build_catalog_marks_excluded_and_unselected() -> None:
    rows = {row["entity_id"]: row for row in _catalog()}
    assert rows["sensor.ignoriert"]["selected"] is False and rows["sensor.ignoriert"]["excluded"] is True
    assert rows["sensor.kueche_leistung"]["selected"] is False and rows["sensor.kueche_leistung"]["excluded"] is False


def test_catalog_digest_is_stable_and_detects_changes() -> None:
    rows = _catalog()
    assert catalog_digest(rows) == catalog_digest(_catalog())
    rows[0]["selected"] = not rows[0]["selected"]
    assert catalog_digest(rows) != catalog_digest(_catalog())


# ---------------------------------------------------------------- Phase 1

from custom_components.zeitarchiv.catalog import build_catalog_body, encode_catalog  # noqa: E402
from custom_components.zeitarchiv.registry_filter import ArchiveFilterMatcher  # noqa: E402


@dataclass
class LabeledEntry(Entry):
    labels: set = field(default_factory=set)


def _phase1_rows(ledger):
    entity_registry = Registry({
        "sensor.a": LabeledEntry(labels={"lbl_za"}),
        "sensor.b": LabeledEntry(),
        "sensor.c": LabeledEntry(device_id="dev1"),
        "sensor.d": LabeledEntry(),
        "sensor.privat": LabeledEntry(),
    })
    device_registry = Registry({"dev1": SimpleNamespace(name="Zähler", name_by_user="Hauptzähler", area_id=None, labels=set())})
    area_registry = Registry({})
    label_registry = SimpleNamespace(async_get_label=lambda lid: SimpleNamespace(name="Zeitarchiv") if lid == "lbl_za" else None)
    options = {
        "entities": ["sensor.b", "sensor.status"],
        "labels": ["lbl_za"],
        "devices": ["dev1"],
        "exclude_entities": ["sensor.privat"],
    }
    matcher = ArchiveFilterMatcher(options, entity_registry, device_registry, area_registry)
    states = [
        SimpleNamespace(entity_id=eid, state=value, attributes={})
        for eid, value in (
            ("sensor.a", "1"), ("sensor.b", "2"), ("sensor.c", "3"), ("sensor.d", "4"),
            ("sensor.privat", "5"), ("sensor.status", "Heizen"),
        )
    ]
    rows = build_catalog(states, entity_registry, device_registry, area_registry, matcher, ledger=ledger, label_registry=label_registry)
    return {row["entity_id"]: row for row in rows}


LEDGER = {
    "label_id": "lbl_za",
    "entries": {
        "sensor.a": {"origin": "assistant", "mode": "label", "topic": "energie", "added_ts": 10.0, "change_id": "j1"},
        "sensor.d": {"origin": "assistant", "mode": "ids", "topic": "wetter", "added_ts": 11.0, "change_id": "j2"},
    },
    "log": [{"id": "j2"}, {"id": "j1"}],
}


def test_catalog_phase1_origin_via_and_drift() -> None:
    rows = _phase1_rows(LEDGER)
    a = rows["sensor.a"]
    assert a["origin"] == "assistant" and a["drifted"] is False and a["topic"] == "energie" and a["added_ts"] == 10.0
    assert a["via"] == [
        {"type": "label", "value": "Zeitarchiv", "level": "entity"},
        {"type": "assistant", "topic": "energie", "mode": "label"},
    ]
    b = rows["sensor.b"]
    assert b["origin"] == "manual" and b["via"] == [{"type": "entity"}] and b["topic"] is None
    assert rows["sensor.c"]["via"] == [{"type": "device", "value": "Hauptzähler"}]
    # Assistenten-ID ist in HA aus "entities" verschwunden: von Hand geändert.
    d = rows["sensor.d"]
    assert d["origin"] is None and d["drifted"] is True and d["via"] == [] and d["topic"] == "wetter"
    privat = rows["sensor.privat"]
    assert privat["selected"] is False and privat["excluded"] is False
    assert privat["excluded_by"] == [{"type": "entity"}]
    status = rows["sensor.status"]
    assert status["text"] is True and rows["sensor.a"]["text"] is False


def test_catalog_phase1_without_ledger_everything_selected_is_manual() -> None:
    rows = _phase1_rows(None)
    assert rows["sensor.a"]["origin"] == "manual"
    assert all(row["drifted"] is False for row in rows.values())
    assert all(row["origin"] is None for row in rows.values() if not row["selected"])


def test_catalog_body_and_size_guard() -> None:
    rows = list(_phase1_rows(LEDGER).values())
    body = build_catalog_body(rows, LEDGER, "Zeitarchiv")
    assert body["label"] == {"id": "lbl_za", "name": "Zeitarchiv"}
    assert body["ledger_count"] == 2 and [item["id"] for item in body["log"]] == ["j2", "j1"]
    assert build_catalog_body(rows, None)["label"] is None
    import json

    assert json.loads(encode_catalog(body)) == body
    filler = [{"entity_id": f"sensor.z{i:04d}", "selected": False, "origin": None, "drifted": False, "excluded_by": [], "name": "x" * 100} for i in range(400)]
    big = {**body, "entities": rows + filler}
    small = json.loads(encode_catalog(big, limit=len(encode_catalog(body)) + 5000))
    ids = {row["entity_id"] for row in small["entities"]}
    assert {row["entity_id"] for row in rows if row["selected"] or row["origin"] or row["drifted"] or row["excluded_by"]} <= ids
    assert len(small["entities"]) < len(big["entities"])
