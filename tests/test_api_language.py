"""Die Integration reicht die Sprache von Home Assistant per Accept-Language an die App weiter —
sonst liefert sie Meldungen (Reparaturen, binary_sensor-Attribute) bei der Einstellung
„Automatisch“ immer auf Deutsch."""

from __future__ import annotations

from unittest.mock import patch

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)

from custom_components.zeitarchiv.api import ZeitarchivClient


class _Resp:
    status_code = 200

    def json(self):
        return {"notices": [], "latest_backup": None}


def test_the_home_assistant_language_is_sent_as_accept_language() -> None:
    client = ZeitarchivClient("localhost", 8127, "token", language="en")
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp()) as get:
        client.get_notices()
    assert get.call_args.kwargs["headers"]["Accept-Language"] == "en"


def test_without_a_language_no_header_is_sent() -> None:
    client = ZeitarchivClient("localhost", 8127, "token")
    with patch("custom_components.zeitarchiv.api.requests.get", return_value=_Resp()) as get:
        client.get_notices()
    assert "Accept-Language" not in get.call_args.kwargs["headers"]
