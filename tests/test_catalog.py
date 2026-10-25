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
