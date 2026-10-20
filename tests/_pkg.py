"""Testhilfe: erlaubt `from custom_components.zeitarchiv.<modul> import ...`, ohne dass
`custom_components/zeitarchiv/__init__.py` ausgeführt wird — das importiert echtes
`homeassistant`, das in dieser Testumgebung nicht installiert ist.

Registriert stattdessen leere Namespace-Pakete mit dem richtigen __path__, sodass
Python die einzelnen Module (const.py, events.py, filtering.py, queue_writer.py)
ganz normal über ihre relativen Imports auflösen kann, ohne __init__.py anzufassen.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _register_namespace_package(dotted_name: str, path: Path) -> None:
    if dotted_name in sys.modules:
        return
    pkg = types.ModuleType(dotted_name)
    pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[dotted_name] = pkg


_register_namespace_package("custom_components", _ROOT / "custom_components")

# Mit installiertem homeassistant (HA-Zeitarchiv, tests/ha/ über
# pytest-homeassistant-custom-component) bleibt das echte Paket unangetastet:
# Ein leerer Platzhalter in sys.modules würde dort sonst die Integration
# selbst ersetzen, und Home Assistant fände kein async_setup_entry mehr.
try:
    import homeassistant  # noqa: F401
except ImportError:
    _register_namespace_package(
        "custom_components.zeitarchiv", _ROOT / "custom_components" / "zeitarchiv"
    )
