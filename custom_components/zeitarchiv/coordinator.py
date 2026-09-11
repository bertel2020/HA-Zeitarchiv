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

from .api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Deutlich seltener als der Schreibpfad (Sekunden-Batches) — Meldungen wie
# "Backup fehlgeschlagen" ändern sich nicht sekündlich, und die App
# berechnet sie ohnehin bei jedem Request live (siehe notices.py dort).
NOTICES_SCAN_INTERVAL = timedelta(seconds=60)


class ZeitarchivNoticesCoordinator(DataUpdateCoordinator[dict]):
    """Pollt /api/notices — liefert {"notices": [...], "latest_backup": {...}
    | None} (siehe api.get_notices() und app/api_routes.py auf der App-
    Seite)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ZeitarchivClient) -> None:
        self.client = client
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_notices_{entry.entry_id}",
            update_interval=NOTICES_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self.client.get_notices)
        except ZeitarchivAuthError as err:
            # /api/notices verlangt denselben Token wie /api/write und wird im
            # Demo-Modus ebenso abgelehnt (die App nutzt dort ein eigenes
            # Datenverzeichnis mit eigenem Token, siehe DEMO_MODUS_PLAN.md) —
            # anders als /api/health liefert sein 401-Body kein demo_mode-Feld.
            # Dieselbe Probe wie queue_writer.py._probe_demo_mode() klärt das
            # separat, bevor wir auf einen echten Verbindungsfehler schließen.
            demo_mode = await self.hass.async_add_executor_job(self._probe_demo_mode)
            if demo_mode:
                _LOGGER.info(
                    "Zeitarchiv-Ziel läuft im Demo-Modus; Meldungen und Backup-Status "
                    "bleiben unbekannt, bis wieder produktiv geschaltet wird"
                )
                return {
                    "notices": [],
                    "latest_backup": None,
                    "demo_mode": True,
                    "unauthenticated": True,
                }
            raise UpdateFailed(str(err)) from err
        except ZeitarchivApiError as err:
            raise UpdateFailed(str(err)) from err

    def _probe_demo_mode(self) -> bool | None:
        """Wie queue_writer.py._probe_demo_mode(): derselbe, gerade
        abgelehnte Token verrät über /api/health trotzdem, ob das Ziel im
        Demo-Modus läuft. Liefert None bei jeder Unklarheit — der Aufrufer
        behandelt None wie False: sicherer Rückfall auf UpdateFailed."""
        try:
            self.client.test_connection()
        except ZeitarchivAuthError as err:
            return err.demo_mode
        except Exception:  # noqa: BLE001 — Probe darf den Update-Versuch nie stören
            return None
        return None  # Probe erfolgreich? Token war doch gültig — kein Demo-Signal
