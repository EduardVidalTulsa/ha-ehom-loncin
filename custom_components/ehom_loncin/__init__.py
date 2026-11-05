"""The EHOM / Loncin portable power station integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EhomCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.SELECT]

type EhomConfigEntry = ConfigEntry[EhomCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EhomConfigEntry) -> bool:
    coordinator = EhomCoordinator(hass, entry.data[CONF_ADDRESS])
    try:
        await coordinator.async_connect()
    except RuntimeError:
        # Device not in range right now; platforms will retry via the
        # coordinator the next time a write/read is attempted.
        pass
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EhomConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_disconnect()
    return unload_ok
