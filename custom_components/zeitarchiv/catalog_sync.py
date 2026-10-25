"""Schickt den Entitäten-Katalog an die App (ROADMAP 1.33, Phase 0).

Angestoßen von den Meldungs-Abrufen der App (jede Minute, siehe
coordinator.py). Gesendet wird nur, wenn die App die Fähigkeit "catalog"
meldet, höchstens alle zehn Minuten neu aufgebaut und nur bei einer Änderung
tatsächlich übertragen. Ein Fehlschlag ist hier folgenlos: der Katalog ist ein
Zusatz, der Schreibpfad bleibt davon unberührt.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import ZeitarchivApiError, ZeitarchivClient, capabilities_from
from .catalog import build_catalog, catalog_digest, energy_roles_from_prefs
from .registry_filter import ArchiveFilterMatcher

_LOGGER = logging.getLogger(__name__)

#: So oft wird der Katalog höchstens neu aufgebaut (Sekunden). Registry-Ereignisse
#: als Auslöser sind für später vorgesehen (ROADMAP 1.33, Phase 1).
REBUILD_INTERVAL = 600


class CatalogSender:
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ZeitarchivClient, filters: ArchiveFilterMatcher
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._client = client
        self._filters = filters
        self._last_attempt = 0.0
        self._last_digest: str | None = None
        self._busy = False

    async def async_handle_notices(self, data: Mapping[str, Any] | None) -> None:
        """Wird bei jedem Meldungs-Abruf aufgerufen."""
        if self._busy or not data or data.get("unauthenticated"):
            return
        if "catalog" not in capabilities_from(data):
            return
        now = time.monotonic()
        if self._last_attempt and now - self._last_attempt < REBUILD_INTERVAL:
            return
        self._busy = True
        self._last_attempt = now
        try:
            rows = build_catalog(
                self._hass.states.async_all(),
                er.async_get(self._hass),
                dr.async_get(self._hass),
                ar.async_get(self._hass),
                self._filters,
                await self._energy_roles(),
            )
            digest = catalog_digest(rows)
            if digest == self._last_digest:
                return
            await self._hass.async_add_executor_job(self._client.post_catalog, rows)
            self._last_digest = digest
            _LOGGER.debug("Katalog an die App gesendet · Ziel=%s · Entitäten=%d", self._entry.title, len(rows))
        except ZeitarchivApiError as err:
            _LOGGER.debug("Katalog konnte nicht gesendet werden: %s", err)
        except Exception:  # der Katalog ist ein Zusatz und darf nichts anderes stören
            _LOGGER.exception("Katalog konnte nicht aufgebaut werden")
        finally:
            self._busy = False

    async def _energy_roles(self) -> dict[str, str]:
        try:
            from homeassistant.components.energy.data import async_get_manager  # noqa: PLC0415

            manager = await async_get_manager(self._hass)
            return energy_roles_from_prefs(manager.data)
        except Exception as err:  # Energie-Dashboard nicht eingerichtet oder nicht ladbar
            _LOGGER.debug("Energie-Einstellungen nicht lesbar: %s", err)
            return {}
