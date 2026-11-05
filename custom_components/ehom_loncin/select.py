"""Charge/discharge SOC limit selectors for the EHOM / Loncin power station."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EhomConfigEntry
from .const import (
    CHARGE_LIMIT_OPTIONS,
    DISCHARGE_LIMIT_OPTIONS,
    DOMAIN,
)

OFFSET_CHARGE_LIMIT = 24
OFFSET_DISCHARGE_LIMIT = 25

SELECTS: tuple[tuple[str, str, int, list[int]], ...] = (
    # (data_key, translation_key, set-field offset, options)
    ("charge_upper", "charge_limit", OFFSET_CHARGE_LIMIT, CHARGE_LIMIT_OPTIONS),
    ("discharge_lower", "discharge_limit", OFFSET_DISCHARGE_LIMIT, DISCHARGE_LIMIT_OPTIONS),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EhomConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        EhomLimitSelect(coordinator, data_key, translation_key, offset, options, entry.unique_id)
        for data_key, translation_key, offset, options in SELECTS
    )


class EhomLimitSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, data_key, translation_key, offset, options, address) -> None:
        super().__init__(coordinator)
        self._data_key = data_key
        self._offset = offset
        self.entity_description = SelectEntityDescription(
            key=data_key, translation_key=translation_key
        )
        self._attr_options = [str(opt) for opt in options]
        self._attr_unique_id = f"{address}_{data_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address or coordinator.address)},
            name="EHOM Power Station",
            manufacturer="Loncin",
        )

    @property
    def current_option(self) -> str | None:
        # The device does not report the configured limit back; this is
        # last-known-set only (None until you pick a value here).
        value = self.coordinator.data.get(self._data_key)
        return None if value is None else str(value)

    async def async_select_option(self, option: str) -> None:
        value = int(option)
        await self.coordinator.async_set_field(self._offset, value)
        self.coordinator.data[self._data_key] = value
        self.coordinator.async_set_updated_data(self.coordinator.data)
