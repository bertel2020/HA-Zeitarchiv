"""Tests für custom_components/zeitarchiv/api.py: get_notices() liefert seit
Roadmap 1.4 "notices" und "latest_backup", seit DEMO_MODUS_PLAN.md Punkt 11
zusätzlich "demo_mode" (siehe api_routes.py auf der App-Seite und
tests/test_notices_route_latest_backup.py dort)."""

from __future__ import annotations

from unittest.mock import patch

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)

from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivClient, capabilities_from


def _client() -> ZeitarchivClient:
    return ZeitarchivClient("localhost", 8127, "token")


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_notices_returns_both_notices_and_latest_backup() -> None:
    payload = {
        "notices": [{"id": "x"}],
        "latest_backup": {"filename": "a.zip", "size_bytes": 1, "finished_at": 1.0},
        "demo_mode": True,
    }
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(payload)):
        result = _client().get_notices()
    assert result == {**payload, "capabilities": [], "ai_config_rev": None}


def test_get_notices_passes_the_app_capabilities_on() -> None:
    """Regression: get_notices() ließ "capabilities" früher fallen. Die
    Tests der Integration mockten die ganze Methode samt Fähigkeiten und
    sahen das nicht — _sync_capabilities() setzte "state" dadurch nach dem
    ersten Abruf auf False zurück, Text-Zustände blieben liegen."""
    payload = {"notices": [], "latest_backup": None, "demo_mode": False, "capabilities": ["state", "ai"]}
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(payload)):
        result = _client().get_notices()
    assert capabilities_from(result) == {"state", "ai"}


def test_get_notices_passes_the_ai_config_rev_on_only_as_an_integer() -> None:
    base = {"notices": [], "latest_backup": None}
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({**base, "ai_config_rev": 7})):
        assert _client().get_notices()["ai_config_rev"] == 7
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({**base, "ai_config_rev": "x"})):
        assert _client().get_notices()["ai_config_rev"] is None


def test_get_notices_defaults_latest_backup_to_none_when_absent() -> None:
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"notices": []})):
        result = _client().get_notices()
    assert result == {"notices": [], "latest_backup": None, "demo_mode": False, "capabilities": [], "ai_config_rev": None}


def test_get_notices_defaults_demo_mode_to_false_when_absent() -> None:
    """Ältere App-Version ohne das Feld (vor DEMO_MODUS_PLAN.md Punkt 11)
    konnte ohnehin nur produktiv laufen — kein Versions-Gate nötig."""
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"notices": []})):
        result = _client().get_notices()
    assert result["demo_mode"] is False


def test_get_notices_rejects_non_bool_demo_mode() -> None:
    payload = {"notices": [], "demo_mode": "yes"}
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(payload)):
        try:
            _client().get_notices()
        except ZeitarchivApiError:
            pass
        else:
            raise AssertionError("erwartete ZeitarchivApiError")


def test_get_notices_rejects_non_dict_latest_backup() -> None:
    payload = {"notices": [], "latest_backup": "nope"}
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(payload)):
        try:
            _client().get_notices()
        except ZeitarchivApiError:
            pass
        else:
            raise AssertionError("erwartete ZeitarchivApiError")


def test_get_notices_rejects_non_list_notices() -> None:
    payload = {"notices": "nope"}
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(payload)):
        try:
            _client().get_notices()
        except ZeitarchivApiError:
            pass
        else:
            raise AssertionError("erwartete ZeitarchivApiError")
