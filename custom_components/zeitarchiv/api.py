"""HTTP-Client für die Zeitarchiv-App.

Nutzt requests statt aiohttp, damit sich die Integration an den bestehenden
Stil in diesem Repo hält (siehe fritzbox_phone/api.py, oscam/api.py) — alle
Aufrufe laufen über hass.async_add_executor_job.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = 10  # Sekunden


class ZeitarchivApiError(Exception):
    """Allgemeiner Fehler beim Sprechen mit der App."""


class ZeitarchivAuthError(ZeitarchivApiError):
    """Der API-Token wurde von der App abgelehnt."""


class ZeitarchivClient:
    """Dünner Wrapper um die REST-API der Zeitarchiv-App."""

    def __init__(self, host: str, port: int, api_token: str) -> None:
        self._base_url = f"http://{host}:{port}"
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def test_connection(self) -> None:
        """Prüft Erreichbarkeit und Token. Wirft bei Fehlschlag."""
        try:
            response = requests.get(
                f"{self._base_url}/api/health", headers=self._headers, timeout=_TIMEOUT
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"App nicht erreichbar: {err}") from err

        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        if response.status_code != 200:
            raise ZeitarchivApiError(
                f"App antwortete mit Status {response.status_code}"
            )

    def write_batch(self, events: list[dict[str, Any]]) -> None:
        """Schickt einen Batch Events an /api/write. Wirft bei Fehlschlag."""
        try:
            response = requests.post(
                f"{self._base_url}/api/write",
                json={"events": events},
                headers=self._headers,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Schreiben fehlgeschlagen: {err}") from err

        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        if response.status_code != 200:
            raise ZeitarchivApiError(
                f"App antwortete beim Schreiben mit Status {response.status_code}: "
                f"{response.text[:200]}"
            )
