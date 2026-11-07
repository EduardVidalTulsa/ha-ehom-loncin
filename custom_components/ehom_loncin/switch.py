"""AC/DC output switches for the EHOM / Loncin EP600 power station.

The app's UI only exposes two user-facing toggles, AC and DC; USB-A,
USB-C, 12V DC and Wireless are read-only sub-outputs gated by the DC
switch, not independently controllable (confirmed against the live app
UI), so no separate "usb_switch" entity is created here even though the
protocol has a field for it.
"""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EhomConfigEntry
from .const import CMD_SET_OUTPUT, DOMAIN, FRAME_LEN_OUTPUT, OFFSET_AC_SWITCH, OFFSET_DC_SWITCH

SWITCHES: tuple[tuple[str, str, int], ...] = (
    # (data_key, translation_key, set-field offset)
    ("ac_switch", "ac_output_switch", OFFSET_AC_SWITCH),
    ("dc_switch", "dc_output_switch", OFFSET_DC_SWITCH),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EhomConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        EhomOutputSwitch(coordinator, data_key, translation_key, offset, entry.unique_id)
        for data_key, translation_key, offset in SWITCHES
    )


class EhomOutputSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator, data_key: str, translation_key: str, offset: int, address: str | None) -> None:
        super().__init__(coordinator)
        self._data_key = data_key
        self._offset = offset
        self.entity_description = SwitchEntityDescription(
            key=data_key, translation_key=translation_key
        )
        self._attr_unique_id = f"{address}_{data_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address or coordinator.address)},
            name="EHOM Power Station",
            manufacturer="Loncin",
            model="EP600",
        )

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get(self._data_key)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_field(CMD_SET_OUTPUT, FRAME_LEN_OUTPUT, self._offset, 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_field(CMD_SET_OUTPUT, FRAME_LEN_OUTPUT, self._offset, 0)
