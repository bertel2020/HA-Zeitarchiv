"""Tests für den Client-Teil des KI-Zugriffs: get_ai_config() und ai_call()."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)

from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivAuthError, ZeitarchivClient


class _Resp:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload, self.status_code = payload, status_code

    def json(self):
        if self._payload is None:
            raise ValueError("kein JSON")
        return self._payload


def _client() -> ZeitarchivClient:
    return ZeitarchivClient("localhost", 8127, "token")


def test_get_ai_config_sends_the_api_id_and_returns_the_body() -> None:
    body = {"enabled": True, "tools": []}
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(body)) as get:
        assert _client().get_ai_config("zeitarchiv_abc") == body
    assert get.call_args.args[0] == "http://localhost:8127/api/ai/config"
    assert get.call_args.kwargs["params"] == {"api_id": "zeitarchiv_abc"}


def test_get_ai_config_errors() -> None:
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({}, 401)):
        with pytest.raises(ZeitarchivAuthError):
            _client().get_ai_config("x")
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"detail": "x"}, 404)):
        with pytest.raises(ZeitarchivApiError):
            _client().get_ai_config("x")
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp(None)):
        with pytest.raises(ZeitarchivApiError):
            _client().get_ai_config("x")


def test_ai_call_returns_error_bodies_instead_of_raising() -> None:
    body = {"error": "ai_disabled", "message": "off"}
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp(body, 403)) as post:
        assert _client().ai_call("get_summary", {"period": "day"}) == (403, body)
    assert post.call_args.args[0] == "http://localhost:8127/api/ai/get_summary"
    assert post.call_args.kwargs["json"] == {"period": "day"}


def test_ai_call_sends_the_account_kind_only_when_known() -> None:
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp({}, 200)) as post:
        _client().ai_call("get_notices", {}, "admin")
        assert post.call_args.kwargs["headers"]["X-Zeitarchiv-Ai-User"] == "admin"
        _client().ai_call("get_notices", {})
        assert "X-Zeitarchiv-Ai-User" not in post.call_args.kwargs["headers"]


def test_ai_call_raises_on_rejected_token_and_unreadable_answers() -> None:
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp({}, 401)):
        with pytest.raises(ZeitarchivAuthError):
            _client().ai_call("get_notices", {})
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp(None, 502)):
        with pytest.raises(ZeitarchivApiError):
            _client().ai_call("get_notices", {})
