"""ZeitarchivClient: Auswahl-Aufträge, Entry-Header und erweiterter Katalog (ROADMAP 1.33)."""

from __future__ import annotations

import json
from unittest.mock import patch

import _pkg  # noqa: F401
import pytest

from custom_components.zeitarchiv.api import ZeitarchivApiError, ZeitarchivClient


class _Resp:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


def test_entry_id_header_only_when_given() -> None:
    assert ZeitarchivClient("h", 1, "t", entry_id="abc")._headers["X-Zeitarchiv-Entry-Id"] == "abc"
    assert "X-Zeitarchiv-Entry-Id" not in ZeitarchivClient("h", 1, "t")._headers


def test_get_notices_passes_selection_rev_through() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"notices": [], "selection_rev": 4})):
        assert client.get_notices()["selection_rev"] == 4
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"notices": [], "selection_rev": True})):
        assert client.get_notices()["selection_rev"] is None
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"notices": []})):
        assert client.get_notices().get("selection_rev") is None


def test_get_selection_jobs() -> None:
    client = ZeitarchivClient("h", 1, "t", entry_id="e1")
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp({"jobs": [{"id": "x"}]})) as get:
        assert client.get_selection_jobs() == [{"id": "x"}]
    assert get.call_args.args[0] == "http://h:1/api/selection/jobs"
    assert get.call_args.kwargs["headers"]["X-Zeitarchiv-Entry-Id"] == "e1"
    for bad in (_Resp({"jobs": "x"}), _Resp(None), _Resp({"jobs": []}, 404)):
        with patch("custom_components.zeitarchiv.api.requests.get", return_value=bad), pytest.raises(ZeitarchivApiError):
            client.get_selection_jobs()


def test_ack_selection_job() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp({"ok": True})) as post:
        assert client.ack_selection_job("j1", "applied", {"sensor.a": {"result": "ok", "mode": "ids"}}) is True
    assert post.call_args.args[0] == "http://h:1/api/selection/ack"
    assert post.call_args.kwargs["json"] == {"job_id": "j1", "status": "applied", "results": {"sensor.a": {"result": "ok", "mode": "ids"}}, "message": None}
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp({"ok": False})):
        assert client.ack_selection_job("j1", "failed", {}) is False
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp(None, 500)), pytest.raises(ZeitarchivApiError):
        client.ack_selection_job("j1", "failed", {})


def test_post_catalog_old_and_extended_body() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch("custom_components.zeitarchiv.api.requests.post", return_value=_Resp({"ok": True})) as post:
        client.post_catalog([{"entity_id": "sensor.a"}])
        assert json.loads(post.call_args.kwargs["data"]) == {"entities": [{"entity_id": "sensor.a"}]}
        client.post_catalog([], label={"id": "l", "name": "Zeitarchiv"}, log=[{"id": "x"}], ledger_count=3)
        assert json.loads(post.call_args.kwargs["data"]) == {
            "entities": [], "label": {"id": "l", "name": "Zeitarchiv"}, "log": [{"id": "x"}], "ledger_count": 3}
        client.post_catalog([], body=b'{"entities":[]}')
        assert post.call_args.kwargs["data"] == b'{"entities":[]}'
