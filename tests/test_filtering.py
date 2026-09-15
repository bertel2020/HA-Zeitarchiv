"""Tests für custom_components/zeitarchiv/filtering.py — reine Python-Asserts, kein Framework."""

from __future__ import annotations

from pathlib import Path

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)

from custom_components.zeitarchiv.filtering import (
    is_state_already_sent,
    is_state_value_change,
    normalize_entity_patterns,
    should_archive,
)


def test_initial_state_is_archived() -> None:
    assert is_state_value_change(None, "21.5") is True


def test_attribute_only_event_is_not_archived() -> None:
    assert is_state_value_change("21.5", "21.5") is False


def test_real_state_change_is_archived() -> None:
    assert is_state_value_change("21.5", "21.6") is True


def test_switch_state_change_is_archived_but_same_state_is_not() -> None:
    assert is_state_value_change("off", "on") is True
    assert is_state_value_change("on", "on") is False


def test_state_without_watermark_entry_is_not_already_sent() -> None:
    """Vor dem ersten erfolgreichen Batch dieser Entität gibt es keinen
    Wasserstand — der Initial-Snapshot darf sie dann nicht überspringen."""
    assert is_state_already_sent(1_700_000_000.0, None) is False


def test_state_older_than_or_equal_to_watermark_is_already_sent() -> None:
    assert is_state_already_sent(1_700_000_000.0, 1_700_000_000.0) is True
    assert is_state_already_sent(1_700_000_000.0, 1_700_000_100.0) is True


def test_state_newer_than_watermark_is_not_already_sent() -> None:
    """Ein echter, neuerer Zustand (z. B. seit dem letzten erfolgreichen
    Batch geändert) muss den Initial-Snapshot weiterhin passieren."""
    assert is_state_already_sent(1_700_000_200.0, 1_700_000_100.0) is False


def test_state_without_last_updated_is_not_already_sent() -> None:
    assert is_state_already_sent(None, 1_700_000_000.0) is False


def test_state_listener_applies_value_change_filter_before_building_event() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "zeitarchiv"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    filter_pos = source.index("if not is_state_value_change(")
    enqueue_pos = source.index("_enqueue_state(new_state)")
    assert filter_pos < enqueue_pos


def test_integration_enqueues_current_states_immediately_when_entry_loads() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "zeitarchiv"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    listener_pos = source.index(
        "remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, _handle_state_changed)"
    )
    snapshot_pos = source.index("hass.states.async_all()")
    assert listener_pos < snapshot_pos
    assert "EVENT_HOMEASSISTANT_STARTED" not in source
    assert "all_states = list(hass.states.async_all())" in source
    assert "_enqueue_state(state) for state in all_states if not _already_sent(state)" in source


def test_watermark_is_loaded_before_queue_writer_starts_and_persisted_on_batch_sent() -> None:
    """__init__.py kann hier nicht ausgeführt werden (braucht echtes
    homeassistant, siehe _pkg.py) — Positions-/Substring-Check wie bei den
    übrigen __init__.py-Tests in dieser Datei. Zwei Dinge müssen stimmen:
    der Wasserstand muss VOR queue_writer.start() geladen sein (sonst
    kennt der allererste Initial-Snapshot ihn noch nicht), und
    on_batch_sent muss verdrahtet sein, sonst wächst der Wasserstand nie."""
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "zeitarchiv"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    load_pos = source.index("await watermark_store.async_load()")
    start_pos = source.index("queue_writer.start()")
    assert load_pos < start_pos
    assert "on_batch_sent=lambda batch: hass.add_job(_persist_watermark, batch)" in source


def test_exclude_wins_over_registry_include() -> None:
    assert (
        should_archive(
            "sensor.uptime",
            included_entity_ids=set(),
            excluded_entity_ids={"sensor.uptime"},
            included_by_registry=True,
        )
        is False
    )


def test_exclude_wins_over_explicit_entity_include() -> None:
    assert (
        should_archive(
            "sensor.uptime",
            included_entity_ids={"sensor.uptime"},
            excluded_entity_ids={"sensor.uptime"},
        )
        is False
    )


def test_registry_include_matches() -> None:
    assert (
        should_archive(
            "sensor.pv_ertrag_gesamt",
            included_entity_ids=set(),
            excluded_entity_ids=set(),
            included_by_registry=True,
        )
        is True
    )


def test_explicit_entity_include_matches() -> None:
    assert (
        should_archive(
            "climate.wohnzimmer",
            included_entity_ids={"climate.wohnzimmer"},
            excluded_entity_ids=set(),
        )
        is True
    )


def test_no_match_without_any_inclusion_source() -> None:
    assert (
        should_archive(
            "light.kueche",
            included_entity_ids=set(),
            excluded_entity_ids=set(),
        )
        is False
    )


def test_pattern_without_domain_matches_object_id_across_domains() -> None:
    for entity_id in ("sensor.device_id", "input_number.user_id"):
        assert should_archive(
            entity_id,
            set(),
            set(),
            ["*_id"],
        )


def test_pattern_with_domain_matches_full_entity_id() -> None:
    assert should_archive(
        "sensor.weather_power",
        set(),
        set(),
        ["sensor.weather_*"],
    )
    assert not should_archive(
        "binary_sensor.weather_power",
        set(),
        set(),
        ["sensor.weather_*"],
    )


def test_exclude_pattern_wins_over_all_includes() -> None:
    assert not should_archive(
        "sensor.weather_raw",
        {"sensor.weather_raw"},
        set(),
        ["sensor.*"],
        ["*_raw"],
    )


def test_pattern_normalization_deduplicates_and_rejects_regex_syntax() -> None:
    assert normalize_entity_patterns(" *_ID \n sensor.weather_*\n*_id ") == [
        "*_id",
        "sensor.weather_*",
    ]
    try:
        normalize_entity_patterns("sensor.[ab]")
    except ValueError as err:
        assert str(err) == "invalid_pattern"
    else:
        raise AssertionError("Klammer-Syntax muss abgelehnt werden")


def _run_all() -> None:
    tests = [obj for name, obj in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
