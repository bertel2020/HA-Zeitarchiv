"""Tests für Label-/Registry-Auswahl und Domain-Altlastmigration."""

from __future__ import annotations

from dataclasses import dataclass, field

import _pkg  # noqa: F401

from custom_components.zeitarchiv.registry_filter import (
    ArchiveFilterMatcher,
    migrate_legacy_domains,
)


@dataclass
class Entry:
    entity_id: str = ""
    device_id: str | None = None
    area_id: str | None = None
    labels: set[str] = field(default_factory=set)


class Registry:
    def __init__(self, entries: dict[str, Entry]) -> None:
        self.entries = entries

    def async_get(self, entry_id: str) -> Entry | None:
        return self.entries.get(entry_id)


class AreaRegistry(Registry):
    def async_get_area(self, area_id: str) -> Entry | None:
        return self.async_get(area_id)


def matcher(
    options: dict,
    *,
    entity: Entry,
    device: Entry | None = None,
    area: Entry | None = None,
) -> ArchiveFilterMatcher:
    return ArchiveFilterMatcher(
        options,
        Registry({entity.entity_id: entity}),
        Registry({entity.device_id: device} if entity.device_id and device else {}),
        AreaRegistry(
            {entity.area_id or (device.area_id if device else ""): area} if area else {}
        ),
    )


def test_direct_entity_label_matches() -> None:
    entity = Entry(entity_id="sensor.temperature", labels={"archive"})
    assert matcher({"labels": ["archive"]}, entity=entity).matches(entity.entity_id)


def test_device_label_matches_and_updates_live() -> None:
    entity = Entry(entity_id="sensor.temperature", device_id="device-1")
    device = Entry(labels=set())
    filters = matcher({"labels": ["archive"]}, entity=entity, device=device)
    assert not filters.matches(entity.entity_id)
    device.labels.add("archive")
    assert filters.matches(entity.entity_id)


def test_area_label_matches_via_device_area() -> None:
    entity = Entry(entity_id="sensor.temperature", device_id="device-1")
    device = Entry(area_id="kitchen")
    area = Entry(labels={"archive"})
    assert matcher(
        {"labels": ["archive"]}, entity=entity, device=device, area=area
    ).matches(entity.entity_id)


def test_exclusion_wins_over_label() -> None:
    entity = Entry(entity_id="sensor.private", labels={"archive"})
    filters = matcher(
        {"labels": ["archive"], "exclude_entities": [entity.entity_id]},
        entity=entity,
    )
    assert not filters.matches(entity.entity_id)
    assert filters.matches(entity.entity_id, apply_exclusions=False)


def test_legacy_domains_become_concrete_entities_and_disappear() -> None:
    migrated = migrate_legacy_domains(
        {"domains": ["sensor"], "entities": ["switch.existing"]},
        ["sensor.b", "light.a", "sensor.a"],
    )
    assert "domains" not in migrated
    assert migrated["entities"] == [
        "switch.existing",
        "sensor.a",
        "sensor.b",
    ]


def test_explain_lists_every_way_without_stopping_at_the_first() -> None:
    entity = Entry(entity_id="sensor.temperature", device_id="device-1", labels={"archive", "zeitarchiv"})
    device = Entry(area_id="kitchen", labels={"archive"})
    area = Entry(labels={"archive"})
    filters = matcher(
        {
            "entities": ["sensor.temperature"],
            "entity_patterns": ["temp*", "sensor.*"],
            "labels": ["archive", "zeitarchiv"],
            "devices": ["device-1"],
            "areas": ["kitchen"],
        },
        entity=entity, device=device, area=area,
    )
    result = filters.explain(entity.entity_id)
    assert result["selected"] is True and result["excluded"] is False
    assert result["via"] == [
        {"type": "entity"},
        {"type": "pattern", "value": "temp*"},
        {"type": "pattern", "value": "sensor.*"},
        {"type": "label", "value": "archive", "level": "entity"},
        {"type": "label", "value": "zeitarchiv", "level": "entity"},
        {"type": "device", "value": "device-1"},
        {"type": "label", "value": "archive", "level": "device"},
        {"type": "area", "value": "kitchen"},
        {"type": "label", "value": "archive", "level": "area"},
    ]
    assert result["excluded_by"] == []


def test_explain_reports_exclusions_and_agrees_with_matches() -> None:
    entity = Entry(entity_id="sensor.private", labels={"archive"})
    filters = matcher(
        {"labels": ["archive"], "exclude_entities": ["sensor.private"], "exclude_entity_patterns": ["priv*"]},
        entity=entity,
    )
    result = filters.explain(entity.entity_id)
    assert result["selected"] is False and result["excluded"] is True
    assert result["excluded_by"] == [{"type": "entity"}, {"type": "pattern", "value": "priv*"}]
    assert result["selected"] == filters.matches(entity.entity_id)


def test_explain_for_unselected_and_unknown_entities() -> None:
    entity = Entry(entity_id="sensor.other")
    filters = matcher({"exclude_entities": ["sensor.other"]}, entity=entity)
    result = filters.explain("sensor.other")
    # Ausgeschlossen, aber über keinen Weg erfasst: excluded bleibt False wie im Katalog.
    assert result == {"selected": False, "excluded": False, "via": [], "excluded_by": [{"type": "entity"}]}
    assert filters.explain("sensor.unbekannt")["via"] == []
    assert matcher({"entities": ["sensor.x"]}, entity=entity).explain("sensor.x")["selected"] is True
