"""Regressionstests für den Demo-Modus-Fallback im Lesepfad
(DEMO_MODUS_PLAN.md Punkt 11.5, „Korrektur nach Live-Verifikation"):
/api/notices verlangt denselben Token wie /api/write und wird im Demo-Modus
ebenso mit 401 abgelehnt — ohne Sonderbehandlung wäre ausgerechnet
ZeitarchivModeSensor (soll „Demo" anzeigen) im Demo-Modus unverfügbar
gewesen. coordinator.py/binary_sensor.py importieren homeassistant, das in
dieser Testumgebung nicht installiert ist (siehe _pkg.py-Docstring) —
deshalb reine Quelltext-Prüfungen nach dem etablierten Muster von
test_notices_coordinator_backup_shape.py, kein Ersatz für einen echten
Verhaltenstest."""

from __future__ import annotations

from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "zeitarchiv"


def test_coordinator_probes_demo_mode_instead_of_failing_on_auth_error() -> None:
    source = (INTEGRATION_DIR / "coordinator.py").read_text(encoding="utf-8")
    assert "except ZeitarchivAuthError as err:" in source
    assert "_probe_demo_mode" in source
    assert '"unauthenticated": True' in source


def test_coordinator_still_raises_update_failed_without_demo_signal() -> None:
    """Ohne erkanntes Demo-Signal bleibt der bisherige Rückfall (UpdateFailed,
    Entities werden "Nicht verfügbar") unverändert — nur der Demo-Modus-401
    bekommt eine Sonderbehandlung, echte Verbindungs-/Tokenfehler nicht."""
    source = (INTEGRATION_DIR / "coordinator.py").read_text(encoding="utf-8")
    assert "raise UpdateFailed(str(err)) from err" in source


def test_binary_sensor_shows_unknown_instead_of_off_when_unauthenticated() -> None:
    source = (INTEGRATION_DIR / "binary_sensor.py").read_text(encoding="utf-8")
    start = source.index("def is_on")
    rest = source[start:]
    end = rest.find("\n    @property", 1)
    is_on_source = rest if end == -1 else rest[:end]

    assert '.get("unauthenticated")' in is_on_source
    assert "return None" in is_on_source
