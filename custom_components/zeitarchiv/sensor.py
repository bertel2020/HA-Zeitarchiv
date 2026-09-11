"""Sensoren für Zeitarchiv.

Zwei unterschiedliche Muster nebeneinander, je nach Datenquelle:

- Diagnose-Sensoren (`_ZeitarchivDiagnosticSensor` und ihre Kinder): bewusst
  alle entity_category=diagnostic (tauchen deshalb nicht im normalen
  Dashboard/der Entitäten-Übersicht auf, sondern nur unter "Diagnose" auf der
  Geräteseite) — Zeitarchiv erzeugt sonst weiterhin keine Entities für die
  archivierten Daten selbst (siehe __init__.py-Docstring). Reines Polling
  (should_poll/update(), Standardintervall) statt eines
  DataUpdateCoordinator: die gelesenen Werte kommen aus dem ohnehin schon im
  Prozess laufenden ZeitarchivQueueWriter (reine Attributzugriffe, kein I/O),
  ein Coordinator wäre hier reiner Mehraufwand ohne Nutzen. Dieselben Werte
  liefert diagnostics.py als Download — hier stehen sie zusätzlich live auf
  der Geräteseite, ohne dafür erst "Diagnose herunterladen" klicken zu müssen.
- `ZeitarchivLatestBackupSensor`: coordinator-basiert wie
  `ZeitarchivHealthBinarySensor` in binary_sensor.py, bewusst KEIN
  entity_category=diagnostic — der Zustandswechsel ist der Automations-
  Trigger für eine eigene Offsite-Kopie des Backups (siehe
  blueprints/automation/zeitarchiv/backup_upload.yaml), eine Diagnose-Entity
  wäre dafür schwerer auffindbar.
- `ZeitarchivModeSensor`: derselbe Coordinator wie `ZeitarchivLatestBackupSensor`
  (dieselbe /api/notices-Antwort liefert seit DEMO_MODUS_PLAN.md Punkt 11
  zusätzlich "demo_mode"), ebenfalls bewusst KEIN entity_category=diagnostic
  — "läuft die verbundene Instanz gerade als Demo?" soll im normalen
  Dashboard auffindbar sein. Ursprünglich (Punkt 11.5) sollte ein Ausfall von
  /api/notices — auch der 401 im Demo-Modus, weil die App dort ein eigenes
  Datenverzeichnis mit eigenem Token nutzt — pauschal auf den Standard-
  `unavailable`-Zustand von `CoordinatorEntity` fallen ("Nicht verbunden").
  Das hätte aber ausgerechnet den Sensor, dessen einzige Aufgabe die Anzeige
  von "Demo" ist, im Demo-Modus unverfügbar gemacht. Seit der Korrektur
  erkennt `ZeitarchivNoticesCoordinator._async_update_data()` diesen Fall
  separat (Probe über /api/health, wie `queue_writer.py._probe_demo_mode()`)
  und liefert dann `{"unauthenticated": True, "demo_mode": True, ...}` statt
  `UpdateFailed` — der Coordinator bleibt "erfolgreich", der Sensor zeigt
  "Demo". "Nicht verbunden" bleibt für echte Erreichbarkeits-/Tokenfehler
  (kein Demo-Signal von /api/health) weiterhin der reguläre `unavailable`-
  Zustand. Die drei Health-`binary_sensor` (backup_failed, entities_inactive,
  health_issue) und `ZeitarchivLatestBackupSensor` lesen dasselbe
  "unauthenticated"-Flag und zeigen dann "Unbekannt" statt "Aus"/eines realen
  Zeitstempels — es gibt im Demo-Modus schlicht keine echten Meldungsdaten,
  und "Aus" würde fälschlich Entwarnung signalisieren.
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeitarchivNoticesCoordinator
from .queue_writer import ZeitarchivQueueWriter


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    queue_writer: ZeitarchivQueueWriter = entry_data["queue_writer"]
    notices_coordinator: ZeitarchivNoticesCoordinator = entry_data["notices_coordinator"]
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
            ZeitarchivLatestBackupSensor(notices_coordinator, entry, device_info),
            ZeitarchivModeSensor(notices_coordinator, entry, device_info),
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


class ZeitarchivLatestBackupSensor(
    CoordinatorEntity[ZeitarchivNoticesCoordinator], SensorEntity
):
    """Zeitpunkt des letzten ERFOLGREICHEN Zeitarchiv-Backups. Bewusst KEIN
    entity_category=diagnostic (Unterschied zu _ZeitarchivDiagnosticSensor
    oben) und coordinator-basiert statt should_poll: der Zustandswechsel ist
    der Automations-Trigger für eine eigene Offsite-Kopie, siehe
    blueprints/automation/zeitarchiv/backup_upload.yaml — eine Diagnose-
    Entity wäre für einen Automations-Trigger schwerer auffindbar, das würde
    den Zweck unterlaufen."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True
    _attr_icon = "mdi:cloud-upload-outline"

    def __init__(
        self,
        coordinator: ZeitarchivNoticesCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_latest_backup"
        self._attr_translation_key = "latest_backup"
        self._attr_device_info = device_info

    def _latest_backup(self) -> dict | None:
        return (self.coordinator.data or {}).get("latest_backup")

    @property
    def native_value(self):
        backup = self._latest_backup()
        if not backup or backup.get("finished_at") is None:
            return None
        return datetime.fromtimestamp(backup["finished_at"], tz=timezone.utc)

    @property
    def extra_state_attributes(self) -> dict:
        backup = self._latest_backup() or {}
        return {"filename": backup.get("filename"), "size_bytes": backup.get("size_bytes")}


class ZeitarchivModeSensor(CoordinatorEntity[ZeitarchivNoticesCoordinator], SensorEntity):
    """Betriebsmodus der verbundenen App-Instanz (Produktiv/Demo-Modus) —
    siehe Modul-Docstring oben für die Begründung von Coordinator-Basis,
    fehlender entity_category=diagnostic und dem dritten, nicht als
    Enum-Wert abgebildeten Mockup-Zustand "Nicht verbunden"."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["produktiv", "demo"]
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZeitarchivNoticesCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_mode"
        self._attr_translation_key = "mode"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return "demo" if self.coordinator.data.get("demo_mode") else "produktiv"

    @property
    def icon(self) -> str:
        return "mdi:flask-outline" if self.native_value == "demo" else "mdi:check-decagram-outline"
