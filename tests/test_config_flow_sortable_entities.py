"""Regressionstest für sortierbare Entity-Selectoren im Options-Flow."""

from __future__ import annotations

import json
import re
from pathlib import Path

CONFIG_FLOW = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "zeitarchiv"
    / "config_flow.py"
)
INTEGRATION_INIT = CONFIG_FLOW.with_name("__init__.py")


def test_include_and_exclude_entity_selectors_are_reorderable() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")

    assert (
        len(
            re.findall(
                r"selector\.EntitySelectorConfig\(\s*multiple=True, reorder=True\s*\)",
                source,
            )
        )
        == 2
    )


def test_labels_are_primary_and_domains_are_removed() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    label_position = source.index("CONF_LABELS, default=")
    additional_position = source.index("CONF_ADDITIONAL_SELECTION): section(")

    assert label_position < additional_position
    assert "LabelSelectorConfig(multiple=True)" in source
    assert "CONF_DOMAINS" not in source
    assert "ARCHIVABLE_DOMAINS" not in source


def test_filter_preview_mentions_decimal_places_in_all_languages() -> None:
    integration_dir = CONFIG_FLOW.parent
    for path in (
        integration_dir / "strings.json",
        integration_dir / "translations" / "de.json",
        integration_dir / "translations" / "en.json",
    ):
        strings = json.loads(path.read_text(encoding="utf-8"))
        preview = strings["options"]["step"]["filter_preview"]["description"]
        assert "{decimal_places}" in preview
        assert "{label_count}" in preview


def test_config_entry_migration_is_registered_in_integration_module() -> None:
    config_flow = CONFIG_FLOW.read_text(encoding="utf-8")
    integration_init = INTEGRATION_INIT.read_text(encoding="utf-8")

    assert "VERSION = 2" in config_flow
    assert "async def async_migrate_entry(" in integration_init
    assert "options=migrated, version=2" in integration_init
