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
# Auswertungen über lange Zeiträume dürfen länger dauern; die App bricht selbst
# vor HAs 60-s-Limit pro MCP-Anfrage ab.
_AI_TIMEOUT = 45


class ZeitarchivApiError(Exception):
    """Allgemeiner Fehler beim Sprechen mit der App."""


class ZeitarchivAuthError(ZeitarchivApiError):
    """Der API-Token wurde von der App abgelehnt.

    demo_mode (DEMO_MODUS_REAUTH_PLAN.md): best-effort aus dem 401-Body von
    /api/health gelesen — True/False, wenn die App-Version das Feld schon
    liefert, sonst None (unbekannt: ältere App-Version, kein JSON-Body,
    o. Ä.). queue_writer.py nutzt das, um vor einem Reauth zu prüfen, ob
    die Ablehnung an einem echten Tokenproblem liegt oder daran, dass das
    Ziel gerade im Demo-Modus läuft — bei None gilt derselbe Rückfall wie
    bei False: normaler Reauth wie bisher."""

    def __init__(self, message: str, *, demo_mode: bool | None = None) -> None:
        super().__init__(message)
        self.demo_mode = demo_mode


class ZeitarchivRejectedError(ZeitarchivApiError):
    """Die App hat den Batch inhaltlich abgelehnt (400/413/422).

    Anders als ein Netzwerkfehler oder 5xx wird ein erneuter Versuch mit
    demselben Batch nie gelingen — queue_writer.py verwirft ihn deshalb,
    statt alle nachfolgenden Messwerte dahinter festzuhalten."""


# Statuscodes, bei denen derselbe Batch nie angenommen wird. 401 hat einen
# eigenen Pfad (Reauth), 404/408/429/5xx bleiben wiederholbar — ein falsch
# konfiguriertes Ziel oder eine überlastete App sollen keine Daten verwerfen.
_REJECTED_STATUS_CODES = frozenset({400, 413, 422})


def _demo_mode_from_error_body(response: requests.Response) -> bool | None:
    """Best-effort: liest demo_mode aus dem 401-Body von /api/health
    ({"detail": {"message": ..., "demo_mode": bool}}, siehe api_routes.py
    dort). Nie ein Fehlschlag hier — ein kaputtes/fehlendes Feld bedeutet
    nur "unbekannt" (None), nicht dass etwas mit der eigentlichen
    401-Behandlung schiefgegangen wäre."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    if not isinstance(detail, dict):
        return None
    demo_mode = detail.get("demo_mode")
    return demo_mode if isinstance(demo_mode, bool) else None


def _json_or_none(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def capabilities_from(payload: Any) -> frozenset[str]:
    """Die Fähigkeiten aus einer Antwort von /api/health oder /api/notices.
    Fehlt das Feld (ältere App) oder ist es kaputt, gilt: keine Fähigkeiten —
    der sichere Rückfall auf das bisherige Verhalten."""
    if not isinstance(payload, dict):
        return frozenset()
    caps = payload.get("capabilities")
    if not isinstance(caps, list):
        return frozenset()
    return frozenset(cap for cap in caps if isinstance(cap, str))


class ZeitarchivClient:
    """Dünner Wrapper um die REST-API der Zeitarchiv-App."""

    def __init__(
        self,
        host: str,
        port: int,
        api_token: str,
        integration_version: str | None = None,
        language: str | None = None,
    ) -> None:
        self._base_url = f"http://{host}:{port}"
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        # Optional, damit die App die Integration in ihren Settings anzeigen
        # und veraltete Versionen erkennen kann (siehe api_routes.py/
        # ha_integration.py auf der App-Seite). Kein Fehlschlag, wenn der
        # Aufrufer die Version nicht kennt (z. B. in Tests).
        if integration_version:
            self._headers["X-Zeitarchiv-Integration-Version"] = integration_version
        # Sprache von Home Assistant: Die App liefert Texte wie Meldungen
        # (Reparaturen, binary_sensor-Attribute) in der Sprache des
        # Accept-Language-Headers, solange ihre Spracheinstellung auf
        # "Automatisch" steht. Ohne Header käme immer Deutsch.
        if language:
            self._headers["Accept-Language"] = language

    def test_connection(self) -> frozenset[str]:
        """Prüft Erreichbarkeit und Token. Wirft bei Fehlschlag.

        Liefert die Fähigkeiten, die die App meldet (z. B. "state" für
        Text-Zustände) — leer bei einer App, die das Feld noch nicht kennt."""
        try:
            response = requests.get(
                f"{self._base_url}/api/health", headers=self._headers, timeout=_TIMEOUT
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"App nicht erreichbar: {err}") from err

        if response.status_code == 401:
            raise ZeitarchivAuthError(
                "API-Token wurde von der App abgelehnt", demo_mode=_demo_mode_from_error_body(response)
            )
        if response.status_code != 200:
            raise ZeitarchivApiError(
                f"App antwortete mit Status {response.status_code}"
            )
        return capabilities_from(_json_or_none(response))

    def get_notices(self) -> dict[str, Any]:
        """Aktuell aktive, nicht stummgeschaltete Meldungen UND das letzte
        erfolgreiche Backup der App (siehe notices.py/api_routes.py dort) —
        Grundlage für Repairs/binary_sensor.py (notices), sensor.py
        (latest_backup) und ZeitarchivModeSensor (demo_mode). Wirft bei
        Fehlschlag, wie test_connection()/write_batch()."""
        try:
            response = requests.get(
                f"{self._base_url}/api/notices", headers=self._headers, timeout=_TIMEOUT
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Meldungen konnten nicht abgerufen werden: {err}") from err

        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        if response.status_code != 200:
            raise ZeitarchivApiError(
                f"App antwortete beim Abrufen der Meldungen mit Status "
                f"{response.status_code}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as err:
            raise ZeitarchivApiError("App lieferte keine gültige JSON-Antwort") from err

        notices = payload.get("notices") if isinstance(payload, dict) else None
        if not isinstance(notices, list):
            raise ZeitarchivApiError("App lieferte eine unerwartete Antwortstruktur")

        latest_backup = payload.get("latest_backup") if isinstance(payload, dict) else None
        if latest_backup is not None and not isinstance(latest_backup, dict):
            raise ZeitarchivApiError("App lieferte eine unerwartete Antwortstruktur")

        # Default False statt Pflichtfeld: eine ältere App-Version ohne
        # dieses Feld (vor DEMO_MODUS_PLAN.md Punkt 11) konnte ohnehin nur
        # produktiv laufen — kein Versions-Gate nötig.
        demo_mode = payload.get("demo_mode", False) if isinstance(payload, dict) else False
        if not isinstance(demo_mode, bool):
            raise ZeitarchivApiError("App lieferte eine unerwartete Antwortstruktur")

        return {"notices": notices, "latest_backup": latest_backup, "demo_mode": demo_mode}

    def ai_call(self, tool: str, arguments: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Ruft ein Lese-Werkzeug der App auf (POST /api/ai/<tool>, ROADMAP 1.31).

        Liefert Statuscode und JSON-Body, auch bei 4xx: Die App erklärt dort
        in ``error``/``message``, was das Modell anders machen soll (z. B.
        ``ai_disabled`` oder ``entity_not_found``) — das gehört unverändert zum
        Modell, nicht in eine Ausnahme. Nur Netzwerkfehler, ein abgelehnter
        Token und unlesbare Antworten werfen."""
        try:
            response = requests.post(
                f"{self._base_url}/api/ai/{tool}",
                json=arguments,
                headers=self._headers,
                timeout=_AI_TIMEOUT,
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Zeitarchiv nicht erreichbar: {err}") from err
        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        body = _json_or_none(response)
        if not isinstance(body, dict):
            raise ZeitarchivApiError(f"App antwortete mit Status {response.status_code} ohne JSON")
        return response.status_code, body

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
        if response.status_code in _REJECTED_STATUS_CODES:
            raise ZeitarchivRejectedError(
                f"App lehnte den Batch mit Status {response.status_code} ab: "
                f"{response.text[:200]}"
            )
        if response.status_code != 200:
            raise ZeitarchivApiError(
                f"App antwortete beim Schreiben mit Status {response.status_code}: "
                f"{response.text[:200]}"
            )
