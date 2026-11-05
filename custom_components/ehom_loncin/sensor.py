"""Sensors for the EHOM / Loncin EP600 power station."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EhomConfigEntry
from .const import DOMAIN

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="soc",
        translation_key="soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="input_power",
        translation_key="input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="output_power",
        translation_key="output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ac_total_input_power",
        translation_key="ac_total_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ac_total_output_power",
        translation_key="ac_total_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dc_total_input_power",
        translation_key="dc_total_input_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dc_total_output_power",
        translation_key="dc_total_output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="device_temperature",
        translation_key="device_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="residue_time",
        translation_key="residue_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="charge_left_time",
        translation_key="charge_left_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="charge_status",
        translation_key="charge_status",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="work_status",
        translation_key="work_status",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="alarm",
        translation_key="alarm",
    ),
    SensorEntityDescription(
        key="ac_charge_mode",
        translation_key="ac_charge_mode",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EhomConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(EhomSensor(coordinator, desc, entry.unique_id) for desc in SENSORS)


class EhomSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description: SensorEntityDescription, address: str | None) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address or coordinator.address)},
            name="EHOM Power Station",
            manufacturer="Loncin",
            model="EP600",
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self.entity_description.key)
