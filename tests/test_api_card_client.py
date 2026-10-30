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
    for status in (400, 404, 413, 429):
        with patch(GET, return_value=_Resp({}, status)), pytest.raises(ZeitarchivCardError) as raised:
            client.get_card_chart(1)
        assert raised.value.status == status
        assert raised.value.route_missing is False
    # Ein Fehler der App ist ein eigener Fall, nicht "nicht erreichbar".
    for status in (500, 502, 503):
        with patch(GET, return_value=_Resp(None, status)), pytest.raises(ZeitarchivCardError) as raised:
            client.get_card_chart(1)
        assert raised.value.status == status
    # Eine 404 ohne JSON kommt von einer Route, die die App (oder ihr nginx) nicht kennt.
    with patch(GET, return_value=_Resp(None, 404)), pytest.raises(ZeitarchivCardError) as raised:
        client.get_card_chart(1)
    assert raised.value.route_missing is True
    for bad in (_Resp(None), _Resp([1])):
        with patch(GET, return_value=bad), pytest.raises(ZeitarchivApiError) as raised:
            client.get_card_chart(1)
        assert not isinstance(raised.value, ZeitarchivCardError)
    assert not issubclass(ZeitarchivCardError, ZeitarchivAuthError)


def test_a_series_is_asked_for_with_fixed_words_and_a_fixed_path() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({"spec_version": 1})) as get:
        client.get_card_series(["sensor.a", "sensor.b"], "7d", "percent", "2026-10-01")
        assert get.call_args.args[0] == "http://h:1/api/card/series"
        assert get.call_args.kwargs["params"] == {
            "entity_ids": "sensor.a,sensor.b", "period": "7d", "style": "percent", "at": "2026-10-01",
        }
        client.get_card_series(["sensor.a"])
        assert get.call_args.kwargs["params"] == {"entity_ids": "sensor.a", "period": "month", "style": "auto"}


@pytest.mark.parametrize(
    "arguments",
    [
        {"entity_ids": []},
        {"entity_ids": [f"sensor.x{n}" for n in range(11)]},
        {"entity_ids": ["sensor.a/../b"]},
        {"entity_ids": ["Sensor.A"]},
        {"entity_ids": ["sensor.a,sensor.b"]},
        {"entity_ids": ["sensor.a&x=1"]},
        {"entity_ids": [5]},
        {"entity_ids": ["sensor.a"], "period": "jahrzehnt"},
        {"entity_ids": ["sensor.a"], "style": "bunt"},
    ],
)
def test_a_series_never_sends_anything_but_ids_and_known_words(arguments: dict) -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET) as get, pytest.raises(ValueError):
        client.get_card_series(**arguments)
    get.assert_not_called()


def test_the_entity_list_goes_to_a_fixed_path_and_a_rejection_is_told_apart() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({"entities": []})) as get:
        assert client.get_card_entities() == {"entities": []}
    assert get.call_args.args[0] == "http://h:1/api/card/entities"
    with patch(GET, return_value=_Resp({}, 400)), pytest.raises(ZeitarchivCardError) as raised:
        client.get_card_series(["sensor.a"])
    assert raised.value.status == 400


def test_a_spark_goes_to_a_fixed_path_with_one_id_and_a_known_range() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({"points": []})) as get:
        client.get_card_spark("sensor.a", "7d")
        assert get.call_args.args[0] == "http://h:1/api/card/spark"
        assert get.call_args.kwargs["params"] == {"entity_id": "sensor.a", "range": "7d"}
        client.get_card_spark("sensor.a")
        assert get.call_args.kwargs["params"]["range"] == "24h"


@pytest.mark.parametrize("arguments", [
    {"entity_id": "sensor.a/../b"}, {"entity_id": "sensor.a,sensor.b"}, {"entity_id": "Sensor.A"}, {"entity_id": 5},
    {"entity_id": "sensor.a", "range_key": "1y"},
])
def test_a_spark_never_sends_anything_but_an_id_and_a_known_range(arguments: dict) -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET) as get, pytest.raises(ValueError):
        client.get_card_spark(**arguments)
    get.assert_not_called()


def test_the_width_goes_along_only_when_known_and_is_bounded() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({})) as get:
        client.get_card_chart(7, None, 600)
        assert get.call_args.kwargs["params"] == {"id": 7, "px": 600}
        client.get_card_chart(7, None, 99999)
        assert get.call_args.kwargs["params"]["px"] == 4000
        client.get_card_chart(7)
        assert "px" not in get.call_args.kwargs["params"]
        client.get_card_series(["sensor.a"], px=300)
        assert get.call_args.kwargs["params"]["px"] == 300


def test_a_table_goes_to_a_fixed_path_with_a_whole_number() -> None:
    client = ZeitarchivClient("h", 1, "t")
    with patch(GET, return_value=_Resp({"table": {}})) as get:
        client.get_card_table(4, "2026-10-01")
        assert get.call_args.args[0] == "http://h:1/api/card/table"
        assert get.call_args.kwargs["params"] == {"id": 4, "at": "2026-10-01"}
        client.get_card_table("5")  # type: ignore[arg-type]
        assert get.call_args.kwargs["params"] == {"id": 5}
    with patch(GET) as get, pytest.raises(ValueError):
        client.get_card_table("5/../x")  # type: ignore[arg-type]
    get.assert_not_called()
