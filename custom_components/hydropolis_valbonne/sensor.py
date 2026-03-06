from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_COORDINATOR,
    DEFAULT_ATTRIBUTION,
    DOMAIN,
    MANUFACTURER,
    SENSOR_DAILY_CONSUMPTION,
    SENSOR_LAST_INDEX,
    SENSOR_MONTHLY_CONSUMPTION,
    SENSOR_YEARLY_CONSUMPTION,
)
from .coordinator import HydropolisValbonneCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HydropolisSensorEntityDescription(SensorEntityDescription):
    """Describe a Hydropolis Valbonne sensor."""

    data_key: str = ""


SENSOR_DESCRIPTIONS: tuple[HydropolisSensorEntityDescription, ...] = (
    HydropolisSensorEntityDescription(
        key=SENSOR_DAILY_CONSUMPTION,
        translation_key=SENSOR_DAILY_CONSUMPTION,
        data_key="daily",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.LITERS,
    ),
    HydropolisSensorEntityDescription(
        key=SENSOR_MONTHLY_CONSUMPTION,
        translation_key=SENSOR_MONTHLY_CONSUMPTION,
        data_key="monthly",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.LITERS,
    ),
    HydropolisSensorEntityDescription(
        key=SENSOR_YEARLY_CONSUMPTION,
        translation_key=SENSOR_YEARLY_CONSUMPTION,
        data_key="yearly",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.LITERS,
    ),
    HydropolisSensorEntityDescription(
        key=SENSOR_LAST_INDEX,
        translation_key=SENSOR_LAST_INDEX,
        data_key="last_index",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hydropolis Valbonne sensors from a config entry."""
    coordinator: HydropolisValbonneCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]

    async_add_entities(
        HydropolisValbonneSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class HydropolisValbonneSensor(
    CoordinatorEntity[HydropolisValbonneCoordinator], SensorEntity
):
    """Representation of a Hydropolis Valbonne sensor."""

    _attr_attribution = DEFAULT_ATTRIBUTION
    _attr_has_entity_name = True
    entity_description: HydropolisSensorEntityDescription

    def __init__(
        self,
        coordinator: HydropolisValbonneCoordinator,
        entry: ConfigEntry,
        description: HydropolisSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=MANUFACTURER,
            manufacturer=MANUFACTURER,
            model="Water meter",
            entry_type=None,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current sensor value."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
