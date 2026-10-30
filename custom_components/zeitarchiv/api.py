"""HTTP-Client für die Zeitarchiv-App.

Nutzt requests statt aiohttp, damit sich die Integration an den bestehenden
Stil in diesem Repo hält (siehe fritzbox_phone/api.py, oscam/api.py) — alle
Aufrufe laufen über hass.async_add_executor_job.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = 10  # Sekunden
# Auswertungen über lange Zeiträume dürfen länger dauern; die App bricht selbst
# vor HAs 60-s-Limit pro MCP-Anfrage ab.
_AI_TIMEOUT = 45
# Der Katalog hat einige tausend Zeilen und wird nur selten gesendet.
_CATALOG_TIMEOUT = 30
# Eine Karte wartet auf die Daten eines Charts, nicht auf eine Auswertung.
_CARD_TIMEOUT = 20


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


class ZeitarchivCardError(ZeitarchivApiError):
    """Die App hat eine Abfrage der Karte nicht beantwortet (404: Chart gibt es
    nicht mehr, 429: zu viele gleichzeitige Abfragen). status trägt den Code,
    damit die Karte den Fall benennen kann."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


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


def _int_or_none(value: Any) -> int | None:
    # bool ist in Python ein int — als Zähler aber sinnlos.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


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
        entry_id: str | None = None,
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
        # Welche Verbindung spricht (ROADMAP 1.33): Die App gibt Auswahl-Aufträge
        # nur an den Eintrag, der zuletzt den Katalog geschickt hat.
        if entry_id:
            self._headers["X-Zeitarchiv-Entry-Id"] = entry_id

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

        # Die Fähigkeiten gehören in die Koordinatordaten: _sync_capabilities()
        # (__init__.py) führt sie daraus jede Minute nach. Fehlten sie hier,
        # fiele "state" nach dem ersten Abruf wieder auf False zurück.
        result = {
            "notices": notices,
            "latest_backup": latest_backup,
            "demo_mode": demo_mode,
            "capabilities": sorted(capabilities_from(payload)),
            # Zählt jede Änderung am KI-Zugriff der App hoch; ai.py holt die
            # Konfiguration neu, sobald sich der Wert ändert. None bei einer App
            # ohne KI-Zugriff.
            "ai_config_rev": payload.get("ai_config_rev") if isinstance(payload.get("ai_config_rev"), int) else None,
        }
        # Zählt Auswahl-Aufträge der App hoch (ROADMAP 1.33); selection_sync.py
        # holt die Aufträge nur bei einer Änderung. Nur vorhanden, wenn die App
        # das Feld liefert — für Leser gilt data.get("selection_rev") → None.
        if "selection_rev" in payload:
            result["selection_rev"] = _int_or_none(payload.get("selection_rev"))
        return result

    def _get_card(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self._base_url}{path}", params=params, headers=self._headers, timeout=_CARD_TIMEOUT
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Zeitarchiv nicht erreichbar: {err}") from err
        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        if response.status_code in (404, 429):
            raise ZeitarchivCardError(f"App antwortete mit Status {response.status_code}", response.status_code)
        body = _json_or_none(response)
        if response.status_code != 200 or not isinstance(body, dict):
            raise ZeitarchivApiError(f"App antwortete mit Status {response.status_code}")
        return body

    def get_card_items(self) -> dict[str, Any]:
        """Gespeicherte Charts für die Auswahl der Lovelace-Karte (GET /api/card/items).
        Eine App ohne die Fähigkeit "cards" kennt die Route nicht (404)."""
        return self._get_card("/api/card/items")

    def get_card_chart(self, chart_id: int, at: str | None = None) -> dict[str, Any]:
        """Einstellungen und Daten eines gespeicherten Charts (GET /api/card/chart).

        Die ID reist als Query-Parameter, nie als Teil des Pfads, und kommt hier
        als int an: so bleibt der Pfad fest und die Integration ein schmaler Weg
        statt eines Proxys für beliebige Abfragen."""
        params: dict[str, Any] = {"id": int(chart_id)}
        if at:
            params["at"] = at
        return self._get_card("/api/card/chart", params)

    def get_ai_config(self, api_id: str) -> dict[str, Any]:
        """Konfiguration des KI-Zugriffs (GET /api/ai/config): ob er eingeschaltet
        ist, welche Werkzeuge mit welchen Texten die App anbietet, der API-Prompt.
        Die ID der LLM-API geht mit, damit die Einstellungsseite der App die
        fertige MCP-Adresse zeigen kann."""
        try:
            response = requests.get(
                f"{self._base_url}/api/ai/config",
                params={"api_id": api_id},
                headers=self._headers,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"KI-Konfiguration nicht abrufbar: {err}") from err
        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        body = _json_or_none(response)
        if response.status_code != 200 or not isinstance(body, dict):
            raise ZeitarchivApiError(f"App antwortete beim Abrufen der KI-Konfiguration mit Status {response.status_code}")
        return body

    def ai_call(
        self, tool: str, arguments: dict[str, Any], account: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Ruft ein Lese-Werkzeug der App auf (POST /api/ai/<tool>, ROADMAP 1.31).

        Liefert Statuscode und JSON-Body, auch bei 4xx: Die App erklärt dort
        in ``error``/``message``, was das Modell anders machen soll (z. B.
        ``ai_disabled`` oder ``entity_not_found``) — das gehört unverändert zum
        Modell, nicht in eine Ausnahme. Nur Netzwerkfehler, ein abgelehnter
        Token und unlesbare Antworten werfen.

        account ("admin" oder "user") sagt der App, mit was für einem Konto der
        Client in Home Assistant angemeldet ist; sie zeigt es nur an (Einstellungen
        → KI-Zugriff → Nutzung), gesperrt wird nichts."""
        headers = {**self._headers, "X-Zeitarchiv-Ai-User": account} if account else self._headers
        try:
            response = requests.post(
                f"{self._base_url}/api/ai/{tool}",
                json=arguments,
                headers=headers,
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

    def post_catalog(
        self,
        entities: list[dict[str, Any]],
        *,
        label: dict[str, str] | None = None,
        log: list[dict[str, Any]] | None = None,
        ledger_count: int | None = None,
        body: bytes | None = None,
    ) -> None:
        """Schickt den Entitäten-Katalog (Metadaten, keine Werte) an /api/catalog
        (ROADMAP 1.33). Wirft bei Fehlschlag; eine App ohne den Endpunkt
        antwortet 404 und meldet die Fähigkeit "catalog" gar nicht erst.

        Seit Phase 1 gehen zusätzlich das verwaltete Label, der Verlauf und die
        Zahl der Ledger-Einträge mit. Eine ältere App ignoriert die Felder.
        ``body`` erlaubt einen bereits kompakt kodierten Body (catalog.encode_catalog)."""
        if body is None:
            payload: dict[str, Any] = {"entities": entities}
            if label is not None or log is not None or ledger_count is not None:
                payload.update({"label": label, "log": log or [], "ledger_count": int(ledger_count or 0)})
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            response = requests.post(
                f"{self._base_url}/api/catalog",
                data=body,
                headers=self._headers,
                timeout=_CATALOG_TIMEOUT,
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Katalog nicht gesendet: {err}") from err
        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        if response.status_code != 200:
            raise ZeitarchivApiError(
                f"App antwortete beim Katalog mit Status {response.status_code}: {response.text[:200]}"
            )

    def get_selection_jobs(self) -> list[dict[str, Any]]:
        """Offene Auswahl-Aufträge der App (GET /api/selection/jobs, ROADMAP 1.33).

        Liefert die rohe Liste; geprüft wird jeder Auftrag erst in
        selection_apply.normalize_job. Wirft bei Fehlschlag."""
        try:
            response = requests.get(
                f"{self._base_url}/api/selection/jobs", headers=self._headers, timeout=_TIMEOUT
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Auswahl-Aufträge nicht abrufbar: {err}") from err
        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        body = _json_or_none(response)
        if response.status_code != 200 or not isinstance(body, dict):
            raise ZeitarchivApiError(f"App antwortete bei den Auswahl-Aufträgen mit Status {response.status_code}")
        jobs = body.get("jobs")
        if not isinstance(jobs, list):
            raise ZeitarchivApiError("App lieferte eine unerwartete Antwortstruktur")
        return jobs

    def ack_selection_job(
        self,
        job_id: str,
        status: str,
        results: dict[str, dict[str, Any]],
        message: str | None = None,
    ) -> bool:
        """Quittiert einen Auftrag (POST /api/selection/ack). True, wenn die App
        ihn angenommen hat; False bei unbekannter oder abgelaufener Auftrags-ID
        (die App antwortet dann ``{"ok": false}``). Wirft bei Netz-/Statusfehlern."""
        payload = {"job_id": job_id, "status": status, "results": results, "message": message}
        try:
            response = requests.post(
                f"{self._base_url}/api/selection/ack",
                json=payload,
                headers=self._headers,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as err:
            raise ZeitarchivApiError(f"Auftrag nicht quittiert: {err}") from err
        if response.status_code == 401:
            raise ZeitarchivAuthError("API-Token wurde von der App abgelehnt")
        body = _json_or_none(response)
        if response.status_code != 200 or not isinstance(body, dict):
            raise ZeitarchivApiError(f"App antwortete beim Quittieren mit Status {response.status_code}")
        return body.get("ok") is True

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
