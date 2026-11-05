"""Config flow for the EHOM / Loncin power station integration."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN


class EhomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EHOM / Loncin power stations."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._address is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data={CONF_ADDRESS: self._address},
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered.get(address, address),
                data={CONF_ADDRESS: address},
            )

        from homeassistant.components import bluetooth

        current_addresses = self._async_current_ids()
        for discovery in bluetooth.async_discovered_service_info(self.hass):
            if discovery.address in current_addresses:
                continue
            self._discovered[discovery.address] = discovery.name or discovery.address

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_ADDRESS): probatio.In(self._discovered)}
            ),
        )
