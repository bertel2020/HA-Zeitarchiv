"""Config- und Options-Flow für Zeitarchiv.

Verbindung (Host/Port/Token) hier im Config-Flow; grobe Filter (Domains/
Entities/Bereiche/Geräte, Exclude, Default-Auflösung/-Aufbewahrung) im
Options-Flow — Einstellungen je Entität leben in der App-eigenen
Oberfläche, nicht hier (Konzept Abschnitt 03).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivClient
from .const import (
    ARCHIVABLE_DOMAINS,
    CONF_API_TOKEN,
    CONF_AREAS,
    CONF_DEVICES,
    CONF_DOMAINS,
    CONF_ENTITIES,
    CONF_ENTITY_PATTERNS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_ENTITY_PATTERNS,
    DEFAULT_PORT,
    DOMAIN,
)
from .filtering import normalize_entity_patterns, should_archive
from .options_transfer import OptionsImportError, export_options, import_options

_LOGGER = logging.getLogger(__name__)

CONF_YAML_CONFIG = "yaml_config"
REPORT_ENTITY_LIMIT = 200


def _pattern_text(value: Any) -> str:
    """Wandelt gespeicherte Muster in den mehrzeiligen Formularwert um."""
    if isinstance(value, str):
        return value
    return "\n".join(value or [])


def _entity_lines(entity_ids: list[str], remaining: int) -> tuple[list[str], int]:
    """Formatiert einen begrenzten Teil der Entity-Liste für die Vorschau."""
    visible = entity_ids[:remaining]
    lines = [f"- `{entity_id}`" for entity_id in visible]
    hidden = len(entity_ids) - len(visible)
    if hidden:
        lines.append(f"- … (+{hidden})")
    return lines, remaining - len(visible)


def _build_filter_report(hass: Any, options: dict[str, Any]) -> dict[str, str]:
    """Erstellt die Vorschau der aktuell tatsächlich aufgelösten Entitäten."""
    # Laufzeitimport vermeidet einen Modulzyklus beim Laden des Config-Flows.
    from . import _resolve_filters

    (
        included_entities,
        included_domains,
        excluded_entities,
        included_patterns,
        excluded_patterns,
    ) = _resolve_filters(hass, options)

    registry = er.async_get(hass)
    state_ids = {state.entity_id for state in hass.states.async_all()}
    registry_ids = {entry.entity_id for entry in registry.entities.values()}
    candidates = state_ids | registry_ids

    def included_before_exclusions(entity_id: str) -> bool:
        return should_archive(
            entity_id,
            entity_id.split(".", 1)[0],
            included_entities,
            included_domains,
            set(),
            included_patterns,
            (),
        )

    def included_after_exclusions(entity_id: str) -> bool:
        return should_archive(
            entity_id,
            entity_id.split(".", 1)[0],
            included_entities,
            included_domains,
            excluded_entities,
            included_patterns,
            excluded_patterns,
        )

    matching = {
        entity_id for entity_id in candidates if included_after_exclusions(entity_id)
    }
    current = sorted(matching & state_ids)
    without_state = sorted(matching - state_ids)
    excluded = sorted(
        entity_id
        for entity_id in candidates
        if included_before_exclusions(entity_id)
        and not included_after_exclusions(entity_id)
    )

    domain_counts: dict[str, int] = {}
    for entity_id in current:
        domain = entity_id.split(".", 1)[0]
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    summary = ", ".join(
        f"`{domain}`: {count}" for domain, count in sorted(domain_counts.items())
    ) or "—"

    remaining = REPORT_ENTITY_LIMIT
    current_lines, remaining = _entity_lines(current, remaining)
    without_state_lines, remaining = _entity_lines(without_state, remaining)
    excluded_lines, remaining = _entity_lines(excluded, remaining)
    limited = (
        remaining == 0
        and (len(current) + len(without_state) + len(excluded))
        > REPORT_ENTITY_LIMIT
    )
    return {
        "current_count": str(len(current)),
        "domain_summary": summary,
        "current_entities": "\n".join(current_lines) or "- —",
        "without_state_count": str(len(without_state)),
        "without_state_entities": "\n".join(without_state_lines) or "- —",
        "excluded_count": str(len(excluded)),
        "excluded_entities": "\n".join(excluded_lines) or "- —",
        "limit_note": (
            f"⚠ {REPORT_ENTITY_LIMIT} / "
            f"{len(current) + len(without_state) + len(excluded)} Entity-IDs"
            if limited
            else ""
        ),
    }


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        # Nur von Home Assistant serialisierbare Standardvalidatoren im
        # Formularschema verwenden. Eigene Python-Callables lassen den Flow
        # bereits beim Laden mit HTTP 500 scheitern; die Leerwertprüfung
        # erfolgt deshalb nach dem Absenden in async_step_user().
        vol.Required(CONF_NAME, default="Produktivsystem"): str,
        vol.Required(CONF_HOST, default="localhost"): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_API_TOKEN): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


async def _validate_input(hass: Any, data: dict[str, Any]) -> None:
    """Testet die Verbindung zur App. Wirft bei Fehlschlag."""
    client = ZeitarchivClient(data[CONF_HOST], data[CONF_PORT], data[CONF_API_TOKEN])
    await hass.async_add_executor_job(client.test_connection)


class ZeitarchivConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Verbindung zur Zeitarchiv-App einrichten."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            else:
                user_input = {**user_input, CONF_NAME: name}
                try:
                    await _validate_input(self.hass, user_input)
                except ZeitarchivAuthError:
                    errors["base"] = "invalid_auth"
                except ZeitarchivApiError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unerwarteter Fehler beim Verbindungstest")
                    errors["base"] = "unknown"
                else:
                    # Ein Home Assistant darf mehrere Zeitarchiv-Ziele parallel
                    # bedienen (z. B. Produktiv- und Testsystem). Deshalb ist der
                    # Endpunkt ausdrücklich keine Config-Entry-Unique-ID: Auch
                    # derselbe Host/Port kann mit einem zweiten benannten Eintrag
                    # eingerichtet werden. Laufzeitdaten und Diagnose-Entities
                    # sind ohnehin über entry.entry_id voneinander getrennt.
                    return self.async_create_entry(
                        title=f"Zeitarchiv ({name})", data=user_input
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Host/Port/Token nachträglich ändern (Einstellungen → Geräte & Dienste →
        Zeitarchiv → Neu konfigurieren) — Gegenstück zur Möglichkeit, den Token
        in der Zeitarchiv-GUI selbst neu zu generieren/zu löschen (Bereich
        "Verbindung"): ohne diesen Schritt gäbe es keine Stelle, den hier
        hinterlegten Token an einen dort geänderten anzupassen."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            else:
                user_input = {**user_input, CONF_NAME: name}
                try:
                    await _validate_input(self.hass, user_input)
                except ZeitarchivAuthError:
                    errors["base"] = "invalid_auth"
                except ZeitarchivApiError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unerwarteter Fehler beim Verbindungstest")
                    errors["base"] = "unknown"
                else:
                    # Der in __init__.py registrierte Update-Listener plant den
                    # einzigen Reload. async_update_reload_and_abort() oder ein
                    # zusätzlicher async_reload() würden ab HA 2026.12 wegen des
                    # doppelten Reload-Mechanismus fehlschlagen.
                    return self.async_update_and_abort(
                        entry,
                        data=user_input,
                        title=f"Zeitarchiv ({name})",
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=entry.data.get(CONF_NAME, "Produktivsystem"),
                    ): str,
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): vol.Coerce(int),
                    vol.Required(
                        CONF_API_TOKEN, default=entry.data[CONF_API_TOKEN]
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Von HA automatisch gestartet, sobald der Queue-Writer einen
        abgelehnten Token meldet (siehe on_auth_failed in __init__.py) — der
        naheliegendste Moment für "Token neu setzen": genau dann, wenn er
        gerade abgelehnt wurde, statt dass man das erst im Log bemerken müsste."""
        self._reauth_entry_data = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**self._reauth_entry_data, CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
            try:
                await _validate_input(self.hass, data)
            except ZeitarchivAuthError:
                errors["base"] = "invalid_auth"
            except ZeitarchivApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unerwarteter Fehler beim Verbindungstest")
                errors["base"] = "unknown"
            else:
                # Wie beim Reconfigure übernimmt ausschließlich der vorhandene
                # Update-Listener den Reload.
                return self.async_update_and_abort(
                    self._get_reauth_entry(), data=data
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return ZeitarchivOptionsFlow()


class ZeitarchivOptionsFlow(config_entries.OptionsFlow):
    """Grobe Filter — Standard-Auflösung/-Aufbewahrung für neu erkannte
    Entitäten werden NICHT hier gepflegt, sondern ausschließlich in der
    App-Oberfläche (Einstellungen → Archivierung): Index.get_or_create_entity()
    liest sie direkt aus der App-eigenen settings-Tabelle, nie aus
    config_entry.options. Ein gleichnamiges Feld hier wäre also reine
    Attrappe ohne jede Wirkung — deshalb bewusst nicht dupliziert."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zeigt ein übersichtliches Menü statt sofort aller Filterfelder."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["filters", "overview", "export", "import"],
        )

    async def async_step_overview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zeigt die mit den gespeicherten Filtern erfassten Entitäten."""
        if user_input is not None:
            return await self.async_step_init()
        return self.async_show_form(
            step_id="overview",
            data_schema=vol.Schema({}),
            description_placeholders=_build_filter_report(
                self.hass, dict(self.config_entry.options)
            ),
        )

    async def async_step_filters(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Bearbeitet die aktiven Archivfilter."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized = dict(user_input)
            try:
                normalized[CONF_ENTITY_PATTERNS] = normalize_entity_patterns(
                    user_input.get(CONF_ENTITY_PATTERNS, "")
                )
            except ValueError as err:
                errors[CONF_ENTITY_PATTERNS] = str(err)
            try:
                normalized[CONF_EXCLUDE_ENTITY_PATTERNS] = normalize_entity_patterns(
                    user_input.get(CONF_EXCLUDE_ENTITY_PATTERNS, "")
                )
            except ValueError as err:
                errors[CONF_EXCLUDE_ENTITY_PATTERNS] = str(err)
            if not errors:
                self._pending_filters = normalized
                return await self.async_step_filter_preview()

        options = self.config_entry.options
        defaults = user_input if user_input is not None else options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DOMAINS,
                    default=defaults.get(CONF_DOMAINS, ARCHIVABLE_DOMAINS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ARCHIVABLE_DOMAINS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_ENTITIES, default=defaults.get(CONF_ENTITIES, [])
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True, reorder=True)
                ),
                vol.Optional(
                    CONF_AREAS, default=defaults.get(CONF_AREAS, [])
                ): selector.AreaSelector(selector.AreaSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_DEVICES, default=defaults.get(CONF_DEVICES, [])
                ): selector.DeviceSelector(selector.DeviceSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_EXCLUDE_ENTITIES,
                    default=defaults.get(CONF_EXCLUDE_ENTITIES, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True, reorder=True)
                ),
                vol.Optional(
                    CONF_ENTITY_PATTERNS,
                    default=_pattern_text(defaults.get(CONF_ENTITY_PATTERNS, [])),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(
                    CONF_EXCLUDE_ENTITY_PATTERNS,
                    default=_pattern_text(
                        defaults.get(CONF_EXCLUDE_ENTITY_PATTERNS, [])
                    ),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
            }
        )
        return self.async_show_form(
            step_id="filters", data_schema=schema, errors=errors
        )

    async def async_step_filter_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zeigt die effektiv erfassten Entitäten vor dem Speichern."""
        pending = getattr(self, "_pending_filters", None)
        if pending is None:
            return await self.async_step_filters()
        if user_input is not None:
            del self._pending_filters
            return self.async_create_entry(title="", data=pending)
        return self.async_show_form(
            step_id="filter_preview",
            data_schema=vol.Schema({}),
            description_placeholders=_build_filter_report(self.hass, pending),
        )

    async def async_step_export(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zeigt eine kopierbare YAML-Fassung ohne Verbindungsdaten/Token."""
        if user_input is not None:
            return await self.async_step_init()
        return self.async_show_form(
            step_id="export",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_YAML_CONFIG,
                        default=export_options(self.config_entry.options),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
        )

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Importiert einen YAML-Export und ersetzt damit die aktiven Filter."""
        errors: dict[str, str] = {}
        yaml_config = ""
        if user_input is not None:
            yaml_config = user_input[CONF_YAML_CONFIG]
            try:
                imported_options = import_options(yaml_config)
            except OptionsImportError as err:
                errors["base"] = str(err)
            else:
                return self.async_create_entry(title="", data=imported_options)

        return self.async_show_form(
            step_id="import",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_YAML_CONFIG, default=yaml_config
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
            errors=errors,
        )
