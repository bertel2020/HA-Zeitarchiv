"""Schickt den Entitäten-Katalog an die App (ROADMAP 1.33).

Angestoßen von den Meldungs-Abrufen der App (jede Minute, siehe
coordinator.py). Gesendet wird nur, wenn die App die Fähigkeit "catalog"
meldet, höchstens alle zehn Minuten neu aufgebaut und nur bei einer Änderung
tatsächlich übertragen. Nach einer vom Assistenten angewendeten Änderung geht
er sofort raus (``async_send_now``: ohne Drosselung und Digest-Prüfung).
Ein Fehlschlag ist hier folgenlos: der Katalog ist ein Zusatz, der
Schreibpfad bleibt davon unberührt.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import ZeitarchivApiError, ZeitarchivClient, capabilities_from
from .catalog import build_catalog, build_catalog_body, catalog_digest, encode_catalog, energy_roles_from_prefs
from .registry_filter import ArchiveFilterMatcher

if TYPE_CHECKING:
    from .selection_sync import SelectionManager

_LOGGER = logging.getLogger(__name__)

#: So oft wird der Katalog höchstens neu aufgebaut (Sekunden).
REBUILD_INTERVAL = 600


def _label_registry(hass: HomeAssistant) -> Any:
    try:
        from homeassistant.helpers import label_registry as lr  # noqa: PLC0415

        return lr.async_get(hass)
    except Exception:  # noqa: BLE001 — ohne Label-Registry nur ohne Namen
        return None


class CatalogSender:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ZeitarchivClient,
        filters: ArchiveFilterMatcher,
        selection: SelectionManager | None = None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._client = client
        self._filters = filters
        self._selection = selection
        self._last_attempt = 0.0
        self._last_digest: str | None = None
        self._busy = False
        self._again = False
        self._capable = False

    async def async_handle_notices(self, data: Mapping[str, Any] | None) -> None:
        """Wird bei jedem Meldungs-Abruf aufgerufen."""
        if not data or data.get("unauthenticated"):
            return
        self._capable = "catalog" in capabilities_from(data)
        if self._busy or not self._capable:
            return
        now = time.monotonic()
        if self._last_attempt and now - self._last_attempt < REBUILD_INTERVAL:
            return
        await self._async_send(force=False)

    async def async_send_now(self) -> None:
        """Sofort senden (nach einer Änderung durch den Assistenten)."""
        if not self._capable:
            return
        if self._busy:
            self._again = True
            return
        await self._async_send(force=True)

    async def _async_send(self, *, force: bool) -> None:
        self._busy = True
        self._last_attempt = time.monotonic()
        try:
            while True:
                self._again = False
                await self._async_build_and_post(force=force)
                if not self._again:
                    break
                force = True
        finally:
            self._busy = False

    async def _async_build_and_post(self, *, force: bool) -> None:
        try:
            ledger = self._selection.ledger if self._selection is not None else None
            labels = _label_registry(self._hass)
            rows = build_catalog(
                self._hass.states.async_all(),
                er.async_get(self._hass),
                dr.async_get(self._hass),
                ar.async_get(self._hass),
                self._filters,
                await self._energy_roles(),
                ledger=ledger,
                label_registry=labels,
            )
            label_name = None
            if ledger and ledger.get("label_id") and labels is not None:
                label = labels.async_get_label(ledger["label_id"])
                label_name = getattr(label, "name", None)
            body = build_catalog_body(rows, ledger, label_name)
            digest = catalog_digest([body])
            if not force and digest == self._last_digest:
                return
            encoded = encode_catalog(body)
            await self._hass.async_add_executor_job(
                lambda: self._client.post_catalog(rows, body=encoded)
            )
            self._last_digest = digest
            _LOGGER.debug("Katalog an die App gesendet · Ziel=%s · Entitäten=%d", self._entry.title, len(rows))
        except ZeitarchivApiError as err:
            _LOGGER.debug("Katalog konnte nicht gesendet werden: %s", err)
        except Exception:  # der Katalog ist ein Zusatz und darf nichts anderes stören
            _LOGGER.exception("Katalog konnte nicht aufgebaut werden")

    async def _energy_roles(self) -> dict[str, str]:
        try:
            from homeassistant.components.energy.data import async_get_manager  # noqa: PLC0415

            manager = await async_get_manager(self._hass)
            return energy_roles_from_prefs(manager.data)
        except Exception as err:  # Energie-Dashboard nicht eingerichtet oder nicht ladbar
            _LOGGER.debug("Energie-Einstellungen nicht lesbar: %s", err)
            return {}
