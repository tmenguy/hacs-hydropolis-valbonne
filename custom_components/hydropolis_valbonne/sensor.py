"""Sensor platform for Hydropolis Valbonne water consumption."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CONTRAT_ID, DOMAIN
from .coordinator import HydropolisConfigEntry, HydropolisCoordinator

ATTRIBUTION = "Data provided by SPL Hydropolis"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HydropolisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hydropolis sensors from a config entry."""
    coordinator = entry.runtime_data
    contrat_id = entry.data[CONF_CONTRAT_ID]
    async_add_entities([HydropolisWaterMeterSensor(coordinator, contrat_id)])


class HydropolisWaterMeterSensor(
    CoordinatorEntity[HydropolisCoordinator], SensorEntity
):
    """Water meter total reading, ever-increasing."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 0
    _attr_translation_key = "water_meter"

    def __init__(
        self,
        coordinator: HydropolisCoordinator,
        contrat_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{contrat_id}_water_meter"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, contrat_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="SPL Hydropolis",
            name=f"Hydropolis {contrat_id}",
        )

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.meter_total_liters

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return {
            "last_measurement": self.coordinator.data.last_measurement.isoformat(),
        }
