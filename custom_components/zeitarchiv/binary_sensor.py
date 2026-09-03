"""Automations-taugliche Health-Entities aus /api/notices.

Bewusst eine Teilmenge der App-Meldungen (siehe notices.py dort, "Bucket B"
der Roadmap-Planung 1.1/1.5) — nur Zustände mit sinnvollem Automations-
Anwendungsfall werden zu Entities, nicht der volle Meldungskatalog (der
bleibt im Zeitarchiv-Glocken-Icon bzw. für kritische Fälle als Repair-Issue,
siehe repairs.py)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeitarchivNoticesCoordinator


@dataclass(frozen=True)
class _HealthSensorSpec:
    key: str
    notice_ids: frozenset[str]


_HEALTH_SENSORS: tuple[_HealthSensorSpec, ...] = (
    _HealthSensorSpec("backup_failed", frozenset({"backup.job_failed"})),
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
        }),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ZeitarchivNoticesCoordinator = hass.data[DOMAIN][entry.entry_id][
        "notices_coordinator"
    ]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Zeitarchiv",
        entry_type="service",
    )
    async_add_entities(
        ZeitarchivHealthBinarySensor(coordinator, entry, device_info, spec)
        for spec in _HEALTH_SENSORS
    )


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
        notices = self.coordinator.data or []
        return [notice for notice in notices if notice.get("id") in self._spec.notice_ids]

    @property
    def is_on(self) -> bool:
        return bool(self._matching_notices())

    @property
    def extra_state_attributes(self) -> dict:
        matches = self._matching_notices()
        return {
            "reasons": [notice["id"] for notice in matches],
            "details": [notice.get("detail") for notice in matches],
        }
