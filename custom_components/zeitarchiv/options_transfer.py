"""Sicherer, portabler YAML-Import/-Export der Zeitarchiv-Filteroptionen."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import yaml

from .const import (
    CONF_AREAS,
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_ENTITY_PATTERNS,
    CONF_LABELS,
)
from .filtering import normalize_entity_patterns
from .registry_filter import LEGACY_CONF_DOMAINS

FORMAT_NAME = "zeitarchiv-options"
FORMAT_VERSION = 3
SUPPORTED_FORMAT_VERSIONS = {1, 2, FORMAT_VERSION}
FILTER_KEYS = (
    CONF_LABELS,
    CONF_ENTITIES,
    CONF_AREAS,
    CONF_DEVICES,
    CONF_EXCLUDE_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITY_PATTERNS,
)
LEGACY_VERSION_1_FILTER_KEYS = (
    LEGACY_CONF_DOMAINS,
    CONF_ENTITIES,
    CONF_AREAS,
    CONF_DEVICES,
    CONF_EXCLUDE_ENTITIES,
)
LEGACY_VERSION_2_FILTER_KEYS = LEGACY_VERSION_1_FILTER_KEYS + (
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITY_PATTERNS,
)
LEGACY_ARCHIVABLE_DOMAINS = {
    "sensor",
    "binary_sensor",
    "switch",
    "climate",
    "input_number",
    "input_boolean",
    "counter",
}

_ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


class OptionsImportError(ValueError):
    """Die importierte Konfiguration ist ungültig oder nicht unterstützt."""


def export_options(options: Mapping[str, Any]) -> str:
    """Gibt ausschließlich portable Filteroptionen als stabiles YAML zurück."""
    filters = {
        key: (
            list(dict.fromkeys(options.get(key, [])))
            if key
            in (
                CONF_ENTITIES,
                CONF_EXCLUDE_ENTITIES,
                CONF_ENTITY_PATTERNS,
                CONF_EXCLUDE_ENTITY_PATTERNS,
            )
            else sorted(set(options.get(key, [])))
        )
        for key in FILTER_KEYS
    }
    document = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "filters": filters,
    }
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def import_options(raw_yaml: str) -> dict[str, list[str]]:
    """Liest und validiert einen vollständigen Zeitarchiv-Filterexport."""
    try:
        document = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as err:
        raise OptionsImportError("invalid_yaml") from err

    if not isinstance(document, dict):
        raise OptionsImportError("invalid_structure")
    if set(document) != {"format", "version", "filters"}:
        raise OptionsImportError("invalid_structure")
    version = document["version"]
    if document["format"] != FORMAT_NAME or version not in SUPPORTED_FORMAT_VERSIONS:
        raise OptionsImportError("unsupported_format")

    filters = document["filters"]
    allowed_keys = (
        LEGACY_VERSION_1_FILTER_KEYS
        if version == 1
        else LEGACY_VERSION_2_FILTER_KEYS
        if version == 2
        else FILTER_KEYS
    )
    if not isinstance(filters, dict) or not set(filters).issubset(allowed_keys):
        raise OptionsImportError("invalid_structure")

    result: dict[str, list[str]] = {}
    for key in FILTER_KEYS:
        values = filters.get(key, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value for value in values
        ):
            raise OptionsImportError("invalid_structure")
        if key in (CONF_ENTITIES, CONF_EXCLUDE_ENTITIES) and any(
            not _ENTITY_ID_PATTERN.fullmatch(value) for value in values
        ):
            raise OptionsImportError("invalid_entity")
        if key in (CONF_ENTITY_PATTERNS, CONF_EXCLUDE_ENTITY_PATTERNS):
            try:
                values = normalize_entity_patterns(values)
            except ValueError as err:
                raise OptionsImportError(str(err)) from err
        result[key] = (
            list(dict.fromkeys(values))
            if key
            in (
                CONF_ENTITIES,
                CONF_EXCLUDE_ENTITIES,
                CONF_ENTITY_PATTERNS,
                CONF_EXCLUDE_ENTITY_PATTERNS,
            )
            else sorted(set(values))
        )

    if version in (1, 2):
        legacy_domains = filters.get(LEGACY_CONF_DOMAINS, [])
        if any(value not in LEGACY_ARCHIVABLE_DOMAINS for value in legacy_domains):
            raise OptionsImportError("invalid_domain")
        result[LEGACY_CONF_DOMAINS] = list(dict.fromkeys(legacy_domains))

    return result
