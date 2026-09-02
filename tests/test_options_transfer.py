"""Tests für den portablen YAML-Transfer der Integrationsfilter."""

from __future__ import annotations

import _pkg  # noqa: F401
import pytest

from custom_components.zeitarchiv.options_transfer import (
    OptionsImportError,
    export_options,
    import_options,
)


def test_export_round_trip_is_stable_and_omits_secrets() -> None:
    options = {
        "labels": ["archive", "energy", "archive"],
        "entities": ["sensor.z", "sensor.a"],
        "areas": ["living_room"],
        "devices": ["abc123"],
        "exclude_entities": ["sensor.private"],
        "entity_patterns": ["sensor.weather_*", "*_power"],
        "exclude_entity_patterns": ["*_raw"],
        "api_token": "must-not-leak",
        "host": "production.local",
    }

    exported = export_options(options)

    assert "must-not-leak" not in exported
    assert "production.local" not in exported
    assert import_options(exported) == {
        "labels": ["archive", "energy"],
        "entities": ["sensor.z", "sensor.a"],
        "areas": ["living_room"],
        "devices": ["abc123"],
        "exclude_entities": ["sensor.private"],
        "entity_patterns": ["sensor.weather_*", "*_power"],
        "exclude_entity_patterns": ["*_raw"],
    }
    assert export_options(import_options(exported)) == exported


def test_import_preserves_entity_order_and_removes_duplicates() -> None:
    imported = import_options(
        "format: zeitarchiv-options\n"
        "version: 1\n"
        "filters:\n"
        "  entities: [sensor.z, sensor.a, sensor.z]\n"
        "  exclude_entities: [sensor.second, sensor.first, sensor.second]\n"
    )

    assert imported["entities"] == ["sensor.z", "sensor.a"]
    assert imported["exclude_entities"] == ["sensor.second", "sensor.first"]
    assert imported["labels"] == []
    assert imported["entity_patterns"] == []
    assert imported["exclude_entity_patterns"] == []
    assert imported["domains"] == []


def test_import_version_one_adds_empty_pattern_lists() -> None:
    imported = import_options(
        "format: zeitarchiv-options\nversion: 1\nfilters:\n  domains: [sensor]\n"
    )

    assert imported["domains"] == ["sensor"]
    assert imported["labels"] == []
    assert imported["entity_patterns"] == []
    assert imported["exclude_entity_patterns"] == []


def test_import_rejects_invalid_pattern() -> None:
    with pytest.raises(OptionsImportError, match="invalid_pattern"):
        import_options(
            "format: zeitarchiv-options\nversion: 3\nfilters:\n"
            "  entity_patterns: ['sensor.[ab]']\n"
        )


@pytest.mark.parametrize(
    "yaml_config",
    [
        "- kein: mapping",
        "format: zeitarchiv-options\nversion: 99\nfilters: {}",
        "format: zeitarchiv-options\nversion: 1\nfilters:\n  unknown: []",
        "format: zeitarchiv-options\nversion: 1\nfilters:\n  domains: [light]",
        "format: zeitarchiv-options\nversion: 1\nfilters:\n  entities: [ungueltig]",
        "format: zeitarchiv-options\nversion: 3\nfilters:\n  domains: [sensor]",
        "format: zeitarchiv-options\nversion: 1\nfilters: [",
    ],
)
def test_import_rejects_invalid_or_unsupported_documents(yaml_config: str) -> None:
    with pytest.raises(OptionsImportError):
        import_options(yaml_config)
