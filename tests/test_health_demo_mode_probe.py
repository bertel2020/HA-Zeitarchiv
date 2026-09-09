"""Tests für custom_components/zeitarchiv/api.py: test_connection() liest seit
DEMO_MODUS_REAUTH_PLAN.md demo_mode aus dem 401-Body von /api/health und
reicht es über ZeitarchivAuthError.demo_mode durch (siehe api_routes.py auf
der App-Seite und tests/test_health_route_demo_mode.py dort)."""

from __future__ import annotations

from unittest.mock import patch

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)

from custom_components.zeitarchiv.api import ZeitarchivAuthError, ZeitarchivClient


def _client() -> ZeitarchivClient:
    return ZeitarchivClient("localhost", 8127, "token")


class _Resp:
    def __init__(self, status_code, payload=None, *, raises_on_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raises_on_json = raises_on_json

    def json(self):
        if self._raises_on_json:
            raise ValueError("kein JSON")
        return self._payload


def test_test_connection_carries_demo_mode_true_on_401() -> None:
    resp = _Resp(401, {"detail": {"message": "…", "demo_mode": True}})
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=resp):
        try:
            _client().test_connection()
        except ZeitarchivAuthError as err:
            assert err.demo_mode is True
        else:
            raise AssertionError("erwartete ZeitarchivAuthError")


def test_test_connection_carries_demo_mode_false_on_401() -> None:
    resp = _Resp(401, {"detail": {"message": "…", "demo_mode": False}})
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=resp):
        try:
            _client().test_connection()
        except ZeitarchivAuthError as err:
            assert err.demo_mode is False
        else:
            raise AssertionError("erwartete ZeitarchivAuthError")


def test_test_connection_demo_mode_is_none_for_an_older_app_without_the_field() -> None:
    """Ältere App-Version: 401-Body ist ein bloßer String-detail wie bisher
    ({"detail": "Ungültiger oder fehlender API-Token"})."""
    resp = _Resp(401, {"detail": "Ungültiger oder fehlender API-Token"})
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=resp):
        try:
            _client().test_connection()
        except ZeitarchivAuthError as err:
            assert err.demo_mode is None
        else:
            raise AssertionError("erwartete ZeitarchivAuthError")


def test_test_connection_demo_mode_is_none_when_the_body_is_not_json() -> None:
    resp = _Resp(401, raises_on_json=True)
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=resp):
        try:
            _client().test_connection()
        except ZeitarchivAuthError as err:
            assert err.demo_mode is None
        else:
            raise AssertionError("erwartete ZeitarchivAuthError")
