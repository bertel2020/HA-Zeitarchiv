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
from homeassistant.helpers import selector

from .api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivClient
from .const import (
    ARCHIVABLE_DOMAINS,
    CONF_API_TOKEN,
    CONF_AREAS,
    CONF_DEVICES,
    CONF_DOMAINS,
    CONF_ENTITIES,
    CONF_EXCLUDE_ENTITIES,
    DEFAULT_PORT,
    DOMAIN,
)
from .options_transfer import OptionsImportError, export_options, import_options

_LOGGER = logging.getLogger(__name__)

CONF_YAML_CONFIG = "yaml_config"

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
            menu_options=["filters", "export", "import"],
        )

    async def async_step_filters(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Bearbeitet die aktiven Archivfilter."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DOMAINS,
                    default=options.get(CONF_DOMAINS, ARCHIVABLE_DOMAINS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ARCHIVABLE_DOMAINS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_ENTITIES, default=options.get(CONF_ENTITIES, [])
                ): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_AREAS, default=options.get(CONF_AREAS, [])
                ): selector.AreaSelector(selector.AreaSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_DEVICES, default=options.get(CONF_DEVICES, [])
                ): selector.DeviceSelector(selector.DeviceSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_EXCLUDE_ENTITIES, default=options.get(CONF_EXCLUDE_ENTITIES, [])
                ): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            }
        )
        return self.async_show_form(step_id="filters", data_schema=schema)

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
