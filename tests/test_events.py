"""Tests für custom_components/zeitarchiv/events.py — Wertaufbereitung vor dem Enqueue."""

from __future__ import annotations

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)
from custom_components.zeitarchiv.events import build_event


def test_numeric_sensor_parses_to_float() -> None:
    event = build_event("sensor.temp", "sensor", "21.4", "measurement", "°C", 100.0, "Wohnzimmer Temperatur")
    event_id = event.pop("event_id")
    assert len(event_id) == 32
    assert all(char in "0123456789abcdef" for char in event_id)
    assert event == {
        "entity_id": "sensor.temp",
        "domain": "sensor",
        "ts": 100.0,
        "value": 21.4,
        "state_class": "measurement",
        "unit": "°C",
        "friendly_name": "Wohnzimmer Temperatur",
    }


def test_numeric_sensor_is_limited_to_three_decimal_places() -> None:
    event = build_event(
        "sensor.temp", "sensor", "21.45678", "measurement", "°C", 100.0
    )
    assert event["value"] == 21.457


def test_numeric_sensor_does_not_pad_shorter_values() -> None:
    event = build_event(
        "sensor.temp", "sensor", "21.4", "measurement", "°C", 100.0
    )
    assert event["value"] == 21.4


def test_friendly_name_defaults_to_none() -> None:
    event = build_event("sensor.temp", "sensor", "21.4", "measurement", "°C", 100.0)
    assert event["friendly_name"] is None


def test_binary_sensor_on_becomes_one() -> None:
    event = build_event("binary_sensor.tuer", "binary_sensor", "on", None, None, 1.0)
    assert event["value"] == 1.0


def test_binary_sensor_off_becomes_zero() -> None:
    event = build_event("binary_sensor.tuer", "binary_sensor", "off", None, None, 1.0)
    assert event["value"] == 0.0


def test_switch_on_off_normalized_case_insensitive() -> None:
    event = build_event("switch.pumpe", "switch", "ON", None, None, 1.0)
    assert event["value"] == 1.0


def test_unavailable_is_dropped() -> None:
    assert build_event("sensor.temp", "sensor", "unavailable", None, None, 1.0) is None


def test_unknown_is_dropped() -> None:
    assert build_event("sensor.temp", "sensor", "unknown", None, None, 1.0) is None


def test_non_numeric_sensor_text_is_dropped() -> None:
    assert build_event("sensor.wetterbericht", "sensor", "sonnig", None, None, 1.0) is None


def test_binary_sensor_with_unexpected_state_is_dropped() -> None:
    assert build_event("binary_sensor.tuer", "binary_sensor", "problem", None, None, 1.0) is None


def test_device_tracker_home_becomes_one() -> None:
    event = build_event("device_tracker.handy", "device_tracker", "home", None, None, 1.0)
    assert event["value"] == 1.0


def test_device_tracker_not_home_becomes_zero() -> None:
    event = build_event("device_tracker.handy", "device_tracker", "not_home", None, None, 1.0)
    assert event["value"] == 0.0


def test_device_tracker_named_zone_becomes_zero() -> None:
    event = build_event("device_tracker.handy", "device_tracker", "arbeit", None, None, 1.0)
    assert event["value"] == 0.0


def test_person_home_normalized_case_insensitive() -> None:
    event = build_event("person.roberto", "person", "HOME", None, None, 1.0)
    assert event["value"] == 1.0


def test_person_not_home_becomes_zero() -> None:
    event = build_event("person.roberto", "person", "not_home", None, None, 1.0)
    assert event["value"] == 0.0


def _run_all() -> None:
    tests = [obj for name, obj in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()


def test_text_fields_are_cut_to_the_app_limit() -> None:
    """Die App lehnt Texte über 255 Zeichen mit 422 ab — und mit ihnen den
    ganzen Batch. Gekürzt statt verworfen: der Messwert selbst ist gültig."""
    event = build_event(
        "sensor.temp", "sensor", "21.4", "measurement", "x" * 300, 100.0, "N" * 1000
    )
    assert event["unit"] == "x" * 255
    assert event["friendly_name"] == "N" * 255


def test_non_string_attributes_become_text() -> None:
    event = build_event("sensor.temp", "sensor", "21.4", 42, "°C", 100.0, 123)
    assert event["state_class"] == "42"
    assert event["friendly_name"] == "123"


def test_entity_id_the_app_would_reject_is_skipped() -> None:
    # HA erlaubt 255 Zeichen, die App nur 240.
    too_long = "sensor." + "a" * 234
    assert len(too_long) == 241
    assert build_event(too_long, "sensor", "1", None, None, 100.0) is None
    longest = "sensor." + "a" * 233
    assert build_event(longest, "sensor", "1", None, None, 100.0) is not None
