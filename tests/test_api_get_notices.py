"""Tests für custom_components/zeitarchiv/api.py: get_notices() liefert seit
Roadmap 1.4 sowohl "notices" als auch "latest_backup" (siehe api_routes.py
auf der App-Seite und tests/test_notices_route_latest_backup.py dort)."""

from __future__ import annotations

from unittest.mock import patch

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)

from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivClient


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
    }
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(payload)):
        result = _client().get_notices()
    assert result == payload


def test_get_notices_defaults_latest_backup_to_none_when_absent() -> None:
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"notices": []})):
        result = _client().get_notices()
    assert result == {"notices": [], "latest_backup": None}


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
