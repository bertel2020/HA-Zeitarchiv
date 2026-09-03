"""DataUpdateCoordinator für Meldungen aus der Zeitarchiv-App (/api/notices).

Anders als die Diagnose-Sensoren in sensor.py (reines Polling von bereits im
Prozess vorhandenem Zustand, siehe deren Docstring) holt dieser Coordinator
tatsächlich externe Daten von der App — genau der Fall, für den ein
DataUpdateCoordinator gedacht ist (Vorbild: fritzbox_phone/oscam). Grundlage
für binary_sensor.py (Automations-Trigger) und repairs.py (Home-Assistant-
Repairs) — betrifft ausschließlich den Rückkanal App → HA, nicht den
Schreibpfad (state_changed → Queue-Writer) aus __init__.py."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZeitarchivApiError, ZeitarchivClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Deutlich seltener als der Schreibpfad (Sekunden-Batches) — Meldungen wie
# "Backup fehlgeschlagen" ändern sich nicht sekündlich, und die App
# berechnet sie ohnehin bei jedem Request live (siehe notices.py dort).
NOTICES_SCAN_INTERVAL = timedelta(seconds=60)


class ZeitarchivNoticesCoordinator(DataUpdateCoordinator[list[dict]]):
    """Pollt /api/notices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ZeitarchivClient) -> None:
        self.client = client
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_notices_{entry.entry_id}",
            update_interval=NOTICES_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> list[dict]:
        try:
            return await self.hass.async_add_executor_job(self.client.get_notices)
        except ZeitarchivApiError as err:
            raise UpdateFailed(str(err)) from err
