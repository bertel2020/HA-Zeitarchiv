"""Automations-taugliche Health-Entities aus /api/notices.

Bewusst eine Teilmenge der App-Meldungen (siehe notices.py dort, "Bucket B"
der Roadmap-Planung 1.1/1.5) — nur Zustände mit sinnvollem Automations-
Anwendungsfall werden zu Entities, nicht der volle Meldungskatalog (der
bleibt im Zeitarchiv-Glocken-Icon bzw. für kritische Fälle als Repair-Issue,
siehe repairs.py).

Ausnahme: `ZeitarchivTextStatesBinarySensor` kommt nicht aus den Meldungen,
sondern aus dem Schreibpfad der Integration (siehe __init__.py) — nur sie
sieht ausgewählte Entitäten, die Text liefern; die App erfährt von ihnen nie
etwas."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_TEXT_STATES
from .coordinator import ZeitarchivNoticesCoordinator
from .data import ZeitarchivConfigEntry


@dataclass(frozen=True)
class _HealthSensorSpec:
    key: str
    notice_ids: frozenset[str]


_HEALTH_SENSORS: tuple[_HealthSensorSpec, ...] = (
    # backup.external_failed: das lokale Backup ist in Ordnung, nur die Kopie auf
    # das externe Ziel (Netzwerkspeicher/WebDAV) fehlt. Bewusst hier und nicht
    # als Repair (siehe repairs.py): die App wiederholt die Übertragung selbst
    # beim nächsten erfolgreichen Backup, und wer sich auf die externe Kopie
    # verlässt, will genau diesen Zustand automatisieren können.
    _HealthSensorSpec("backup_failed", frozenset({"backup.job_failed", "backup.external_failed"})),
    _HealthSensorSpec(
        "entities_inactive",
        frozenset({
            "housekeeping.inactive_entities_error",
            "housekeeping.inactive_entities_warn",
            "housekeeping.inactive_entities_info",
        }),
    ),
    _HealthSensorSpec(
        "health_issue",
        frozenset({
            "system.storage_reconcile_errors",
            "retention.job_failed",
            "housekeeping.purge_available",
            "housekeeping.host_disk_space_low",
            "system.index_optimization",
            # Kein eigener Sensor: eine hohe Duplikatquote im Ingest ist wie
            # die übrigen hier ein "lohnt einen Blick"-Zustand, kein hartes
            # Problem — Details stehen wie bei allen anderen in
            # extra_state_attributes (reasons/details).
            "ingest.duplicate_ratio_high",
        }),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeitarchivConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.notices_coordinator
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Zeitarchiv",
        entry_type="service",
    )
    entities: list[BinarySensorEntity] = [
        ZeitarchivHealthBinarySensor(coordinator, entry, device_info, spec)
        for spec in _HEALTH_SENSORS
    ]
    entities.append(
        ZeitarchivTextStatesBinarySensor(entry, device_info, entry.runtime_data.text_states)
    )
    async_add_entities(entities)


class ZeitarchivHealthBinarySensor(
    CoordinatorEntity[ZeitarchivNoticesCoordinator], BinarySensorEntity
):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZeitarchivNoticesCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        spec: _HealthSensorSpec,
    ) -> None:
        super().__init__(coordinator)
        self._spec = spec
        self._attr_unique_id = f"{entry.entry_id}_{spec.key}"
        # translation_key statt fest verdrahtetem _attr_name, siehe gleiches
        # Vorgehen in sensor.py.
        self._attr_translation_key = spec.key
        self._attr_device_info = device_info

    def _matching_notices(self) -> list[dict]:
        notices = (self.coordinator.data or {}).get("notices", [])
        return [notice for notice in notices if notice.get("id") in self._spec.notice_ids]

    @property
    def is_on(self) -> bool | None:
        # "unauthenticated" (coordinator.py): Demo-Modus-Fallback ohne echte
        # Meldungsdaten von der App — None zeigt "Unbekannt" statt fälschlich
        # "Aus" (kein Problem erkannt), obwohl schlicht nichts geprüft wurde.
        if (self.coordinator.data or {}).get("unauthenticated"):
            return None
        return bool(self._matching_notices())

    @property
    def extra_state_attributes(self) -> dict:
        matches = self._matching_notices()
        return {
            "reasons": [notice["id"] for notice in matches],
            "details": [notice.get("detail") for notice in matches],
        }


class ZeitarchivTextStatesBinarySensor(BinarySensorEntity):
    """An, solange ausgewählte Entitäten Text statt einer Zahl liefern.

    Gegenstück zur Repair-Karte "text_states_not_archived" (repairs.py) für
    Dashboards und Automationen. Anders als die Karte nennt das Attribut
    `entities` die vollständige Liste. Push statt Polling: __init__.py
    sendet bei jeder Änderung ein Dispatcher-Signal. Kein "Unbekannt" im
    Demo-Modus wie bei ZeitarchivHealthBinarySensor — die Prüfung läuft
    vollständig in der Integration und braucht keine Meldungsdaten der App.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "text_states"

    def __init__(
        self,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        text_states: dict[str, tuple[str, ...]],
    ) -> None:
        self._entry_id = entry.entry_id
        self._text_states = text_states
        self._attr_unique_id = f"{entry.entry_id}_text_states"
        self._attr_device_info = device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_TEXT_STATES.format(self._entry_id),
                self._handle_text_states_changed,
            )
        )

    @callback
    def _handle_text_states_changed(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return bool(self._text_states["entities"])

    @property
    def extra_state_attributes(self) -> dict:
        entities = self._text_states["entities"]
        return {"entities": list(entities), "count": len(entities)}
