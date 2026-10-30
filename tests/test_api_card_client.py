"""ZeitarchivClient: Abrufe für die Lovelace-Karte."""

from __future__ import annotations

from unittest.mock import patch

import _pkg  # noqa: F401
import pytest

from custom_components.zeitarchiv.api import (
    ZeitarchivApiError,
    ZeitarchivAuthError,
    ZeitarchivCardError,
    ZeitarchivClient,
)


class _Resp:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


GET = "custom_components.zeitarchiv.api.requests.get"


def test_items_go_to_a_fixed_path() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({"items": []})) as get:
        assert client.get_card_items() == {"items": []}
    assert get.call_args.args[0] == "http://h:1/api/card/items"
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer t"


def test_the_chart_id_travels_as_a_query_parameter_never_in_the_path() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({"spec_version": 1})) as get:
        client.get_card_chart(7)
        assert get.call_args.args[0] == "http://h:1/api/card/chart"
        assert get.call_args.kwargs["params"] == {"id": 7}
        client.get_card_chart("12", "2026-10-01")  # type: ignore[arg-type]
        assert get.call_args.args[0] == "http://h:1/api/card/chart"
        assert get.call_args.kwargs["params"] == {"id": 12, "at": "2026-10-01"}


def test_text_instead_of_a_number_is_never_sent() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET) as get, pytest.raises(ValueError):
        client.get_card_chart("7/../x")  # type: ignore[arg-type]
    get.assert_not_called()


def test_failures_are_told_apart() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({}, 401)), pytest.raises(ZeitarchivAuthError):
        client.get_card_items()
    for status in (404, 429):
        with patch(GET, return_value=_Resp({}, status)), pytest.raises(ZeitarchivCardError) as raised:
            client.get_card_chart(1)
        assert raised.value.status == status
    for bad in (_Resp({}, 500), _Resp(None), _Resp([1])):
        with patch(GET, return_value=bad), pytest.raises(ZeitarchivApiError):
            client.get_card_chart(1)
    assert not issubclass(ZeitarchivCardError, ZeitarchivAuthError)
