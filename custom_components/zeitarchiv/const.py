"""Konstanten für die Zeitarchiv-Integration."""

from __future__ import annotations

DOMAIN = "zeitarchiv"

# Config-Flow (Verbindung)
CONF_API_TOKEN = "api_token"
DEFAULT_PORT = 8127

# Options-Flow (grobe Filter — Standard-Auflösung/-Aufbewahrung werden
# bewusst NICHT hier gepflegt, siehe Docstring von ZeitarchivOptionsFlow)
CONF_DOMAINS = "domains"
CONF_ENTITIES = "entities"
CONF_AREAS = "areas"
CONF_DEVICES = "devices"
CONF_EXCLUDE_ENTITIES = "exclude_entities"

# Domains, die sinnvoll archivierbar sind (Vorauswahl im Options-Flow).
ARCHIVABLE_DOMAINS = [
    "sensor",
    "binary_sensor",
    "switch",
    "climate",
    "input_number",
    "input_boolean",
    "counter",
]

# Queue/Batch — Vorbild: die Queue/Batch/Retry-Mechanik der HA-Core-InfluxDB-Integration.
MAX_QUEUE_SIZE = 5000
BATCH_SIZE = 100
BATCH_TIMEOUT = 5  # Sekunden
# Nach Erreichen von 60 Sekunden bleibt der Writer bei diesem Intervall und
# verwirft den Batch nicht. So überlebt der Schreibpfad auch längere App-
# Neustarts/Updates, ohne Home Assistant oder dessen Event-Loop zu blockieren.
RETRY_DELAYS = (1, 2, 4, 8, 15, 30, 60)

# Domains, deren Zustand als Schalter (on/off → 1/0) archiviert wird,
# unabhängig von state_class (die haben ohnehin meist keine).
SWITCH_DOMAINS = {"binary_sensor", "switch", "input_boolean"}

# Zustände, die nie archiviert werden.
IGNORED_STATES = {"unavailable", "unknown", "none", ""}
