"""Konstanten für die Zeitarchiv-Integration."""

from __future__ import annotations

DOMAIN = "zeitarchiv"

# Config-Flow (Verbindung)
CONF_API_TOKEN = "api_token"
DEFAULT_PORT = 8127

# Options-Flow (grobe Filter — Standard-Auflösung/-Aufbewahrung werden
# bewusst NICHT hier gepflegt, siehe Docstring von ZeitarchivOptionsFlow)
CONF_LABELS = "labels"
CONF_ENTITIES = "entities"
CONF_AREAS = "areas"
CONF_DEVICES = "devices"
CONF_EXCLUDE_ENTITIES = "exclude_entities"
CONF_ENTITY_PATTERNS = "entity_patterns"
CONF_EXCLUDE_ENTITY_PATTERNS = "exclude_entity_patterns"
CONF_DECIMAL_PLACES = "decimal_places"
# 3 Nachkommastellen war bisher der fest verdrahtete Wert (siehe events.py) —
# als Default beibehalten, damit bestehende Installationen ihr Verhalten
# nicht stillschweigend ändern.
DEFAULT_DECIMAL_PLACES = 3

# Queue/Batch — Vorbild: die Queue/Batch/Retry-Mechanik der HA-Core-InfluxDB-Integration.
MAX_QUEUE_SIZE = 5000
BATCH_SIZE = 100
BATCH_TIMEOUT = 5  # Sekunden
# Nach Erreichen von 60 Sekunden bleibt der Writer bei diesem Intervall und
# verwirft den Batch nicht. So überlebt der Schreibpfad auch längere App-
# Neustarts/Updates, ohne Home Assistant oder dessen Event-Loop zu blockieren.
RETRY_DELAYS = (1, 2, 4, 8, 15, 30, 60)

# Grenzen von /api/write in der App (limits.py bzw. storage/paths.py). Ein
# Event darüber lehnt die App mit 422 ab — die Integration hält sich deshalb
# schon vor dem Enqueue daran (siehe events.py).
APP_EVENT_TEXT_MAX_LENGTH = 255
APP_ENTITY_ID_MAX_LENGTH = 240

# Domains, deren Text-Zustand auch bei Auswahl über Label/Gerät/Bereich/Muster
# archiviert wird (sonst nur bei einzeln ausgewählten Entitäten). Ein Thermostat
# ("heat"/"auto"/"off") ist ein Zustand, den man nicht einzeln anklicken will —
# bei sensor.* wären es dagegen Versionsnummern, Geräte-IDs & Co.
TEXT_STATE_DOMAINS = frozenset({"climate"})

# Domains, deren Zustand als Schalter (on/off → 1/0) archiviert wird,
# unabhängig von state_class (die haben ohnehin meist keine). Nur Domains,
# deren Zustand wirklich ausschließlich on/off ist — climate, media_player,
# cover, lock & Co. zeigen zwar teils "on"/"off", haben aber weitere Zustände
# und gehören nicht hierher. Bei automation heißt "on" aktiviert (nicht:
# läuft gerade), bei script läuft gerade, bei update Update verfügbar, bei
# calendar Termin aktiv.
SWITCH_DOMAINS = {
    "binary_sensor",
    "switch",
    "input_boolean",
    "light",
    "fan",
    "automation",
    "script",
    "remote",
    "siren",
    "humidifier",
    "update",
    "calendar",
}

# Domains mit Anwesenheits-Zuständen ("home"/"not_home"/Zonenname statt
# "on"/"off") — werden wie SWITCH_DOMAINS als Schalter archiviert (Zuhause →
# 1, alles andere, auch eine benannte Zone ungleich "home" → 0), nur das
# State-Vokabular unterscheidet sich.
PRESENCE_DOMAINS = {"device_tracker", "person"}

# Zustände, die nie archiviert werden.
IGNORED_STATES = {"unavailable", "unknown", "none", ""}

# Dispatcher-Signal (je Config-Entry formatiert) für die Liste der
# ausgewählten Entitäten mit Textwerten — __init__.py sendet,
# binary_sensor.ZeitarchivTextStatesBinarySensor hört zu.
SIGNAL_TEXT_STATES = f"{DOMAIN}_text_states_{{}}"
