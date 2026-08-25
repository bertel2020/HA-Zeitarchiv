"""Diagnose-Sensoren für Zeitarchiv.

Bewusst nur eine Handvoll, alle entity_category=diagnostic (tauchen deshalb
nicht im normalen Dashboard/der Entitäten-Übersicht auf, sondern nur unter
"Diagnose" auf der Geräteseite) — Zeitarchiv erzeugt sonst weiterhin keine
Entities für die archivierten Daten selbst (siehe __init__.py-Docstring).

Reines Polling (should_poll/update(), Standardintervall) statt eines
DataUpdateCoordinator: die gelesenen Werte kommen aus dem ohnehin schon im
Prozess laufenden ZeitarchivQueueWriter (reine Attributzugriffe, kein I/O),
ein Coordinator wäre hier reiner Mehraufwand ohne Nutzen. Dieselben Werte
liefert diagnostics.py als Download — hier stehen sie zusätzlich live auf
der Geräteseite, ohne dafür erst "Diagnose herunterladen" klicken zu müssen.
"""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .queue_writer import ZeitarchivQueueWriter


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    queue_writer: ZeitarchivQueueWriter = hass.data[DOMAIN][entry.entry_id]["queue_writer"]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Zeitarchiv",
        entry_type="service",
    )
    async_add_entities(
        [
            ZeitarchivLastSuccessSensor(queue_writer, entry, device_info),
            ZeitarchivSentCountSensor(queue_writer, entry, device_info),
            ZeitarchivQueueSizeSensor(queue_writer, entry, device_info),
            ZeitarchivDroppedSensor(queue_writer, entry, device_info),
        ]
    )


class _ZeitarchivDiagnosticSensor(SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True
    _attr_has_entity_name = True

    def __init__(
        self,
        queue_writer: ZeitarchivQueueWriter,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        key: str,
    ) -> None:
        self._queue_writer = queue_writer
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        # translation_key statt fest verdrahtetem _attr_name — Name kommt aus
        # strings.json/translations/*.json (Abschnitt entity.sensor.<key>),
        # damit englischsprachige HA-Instanzen nicht die deutschen Namen der
        # übrigen Config-/Options-Flow-Texte bekommen.
        self._attr_translation_key = key
        self._attr_device_info = device_info


class ZeitarchivLastSuccessSensor(_ZeitarchivDiagnosticSensor):
    """Zeitpunkt des letzten erfolgreich an die App geschickten Batches —
    dieselbe Semantik wie last_success_seconds_ago in diagnostics.py, hier
    als absoluter Zeitstempel (HA rechnet die "vor X"-Anzeige selbst um)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cloud-check-outline"

    def __init__(self, queue_writer, entry, device_info) -> None:
        super().__init__(queue_writer, entry, device_info, "last_success")

    def update(self) -> None:
        ts = self._queue_writer.last_success_ts
        self._attr_native_value = datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else None


class ZeitarchivQueueSizeSensor(_ZeitarchivDiagnosticSensor):
    """Wartende Events im Hintergrund-Thread — dauerhaft > 0 deutet auf eine
    nicht erreichbare App hin (siehe queue.queue_size in diagnostics.py)."""

    _attr_native_unit_of_measurement = "Events"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:tray-full"

    def __init__(self, queue_writer, entry, device_info) -> None:
        super().__init__(queue_writer, entry, device_info, "queue_size")

    def update(self) -> None:
        self._attr_native_value = self._queue_writer.queue_size


class ZeitarchivSentCountSensor(_ZeitarchivDiagnosticSensor):
    """Erfolgreich an die App übertragene Datensätze seit dem letzten Start.

    Der Writer erhöht den Zähler erst, nachdem die App den gesamten Batch
    bestätigt hat. Fehlgeschlagene und erneut versuchte Übertragungen werden
    daher nicht mehrfach gezählt.
    """

    _attr_native_unit_of_measurement = "Events"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:database-arrow-up-outline"

    def __init__(self, queue_writer, entry, device_info) -> None:
        super().__init__(queue_writer, entry, device_info, "sent_count")

    def update(self) -> None:
        self._attr_native_value = self._queue_writer.sent_count


class ZeitarchivDroppedSensor(_ZeitarchivDiagnosticSensor):
    """Wegen voller Warteschlange verworfene Events seit dem letzten Neustart
    der Integration — TOTAL_INCREASING statt TOTAL, weil der Zähler bei
    jedem Neustart bewusst wieder bei 0 anfängt (kein historischer Zähler,
    siehe dropped_count_since_start in diagnostics.py)."""

    _attr_native_unit_of_measurement = "Events"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:delete-alert-outline"

    def __init__(self, queue_writer, entry, device_info) -> None:
        super().__init__(queue_writer, entry, device_info, "dropped_count")

    def update(self) -> None:
        self._attr_native_value = self._queue_writer.dropped_count
