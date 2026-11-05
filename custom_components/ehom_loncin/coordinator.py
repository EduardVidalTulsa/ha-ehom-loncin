"""BLE connection and protocol handling for the EHOM / Loncin EP600 power station."""

from __future__ import annotations

import logging
import zlib

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BOOL_FIELDS,
    CHAR_NOTIFY,
    CHAR_WRITE,
    CMD_SET_FIELD,
    FRAME_FIELD_MAP,
    FRAME_SENTINEL,
)

_LOGGER = logging.getLogger(__name__)

# Fields the app reads with a sign-extending byte access instead of the
# unsigned c.b() helper.
_SIGNED_BYTE_FIELDS = {"device_temperature"}


def parse_frame(data: bytes) -> dict[str, int] | None:
    """Decode one notify frame into its named fields, if we know its type."""
    if len(data) < 12:
        return None
    frame_type = data[11]
    field_map = FRAME_FIELD_MAP.get(frame_type)
    if field_map is None:
        return None
    result: dict[str, int] = {}
    for name, (offset, width) in field_map.items():
        if offset + width > len(data):
            continue
        raw = data[offset : offset + width]
        if width == 1 and name in _SIGNED_BYTE_FIELDS:
            value = int.from_bytes(raw, "big", signed=True)
        else:
            value = int.from_bytes(raw, "big", signed=False)
        if name in BOOL_FIELDS:
            result[name] = value == 1
        else:
            result[name] = value
    return result


def build_set_field_frame(offset: int, value: int) -> bytes:
    """Build a 'set field' (type 0x32) command frame, as SendBluetoothData.l()."""
    total_len = 25
    payload_len = 12
    frame = bytearray(total_len)
    frame[0] = FRAME_SENTINEL
    frame[1] = 0x3A
    frame[2] = 0x01
    frame[3] = payload_len - 1
    frame[8] = 1
    frame[9] = 1
    frame[10] = 1
    frame[11] = CMD_SET_FIELD
    frame[offset] = 1
    frame[offset + 1] = value & 0xFF
    crc = zlib.crc32(bytes(frame[12 : 12 + payload_len - 1])) & 0xFFFFFFFF
    frame[4] = (crc >> 24) & 0xFF
    frame[5] = (crc >> 16) & 0xFF
    frame[6] = (crc >> 8) & 0xFF
    frame[7] = crc & 0xFF
    return bytes(frame)


class EhomCoordinator(DataUpdateCoordinator[dict[str, int]]):
    """Owns the BLE connection and the latest parsed device data."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(hass, _LOGGER, name="EHOM Loncin", update_interval=None)
        self.address = address
        self._client: BleakClient | None = None
        self.data: dict[str, int] = {}

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def async_connect(self) -> None:
        if self.connected:
            return
        ble_device: BLEDevice | None = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise RuntimeError(f"EHOM device {self.address} not currently in range")

        def _disconnected(_client: BleakClient) -> None:
            _LOGGER.debug("EHOM %s disconnected", self.address)
            self._client = None

        client = await establish_connection(
            BleakClient,
            ble_device,
            self.address,
            disconnected_callback=_disconnected,
        )
        await client.start_notify(CHAR_NOTIFY, self._on_notify)
        self._client = client
        # bleak's BlueZ backend does not request a larger MTU on its own;
        # it stays at the default 23 bytes (20 usable), which is too small
        # for our 25-byte "write-with-response" command frames and causes
        # BlueZ to reject the write ("Unlikely Error"). The app negotiates
        # a 500-byte MTU before writing; ask BlueZ to do the same via its
        # private _acquire_mtu(), since bleak has no public API for this.
        backend = getattr(client, "_backend", None)
        acquire_mtu = getattr(backend, "_acquire_mtu", None)
        if acquire_mtu is not None:
            try:
                await acquire_mtu()
            except Exception:  # noqa: BLE001 - best effort, fall back to default MTU
                _LOGGER.debug("Could not raise MTU for EHOM %s", self.address, exc_info=True)
        _LOGGER.debug(
            "Connected to EHOM %s (mtu=%s)", self.address, getattr(client, "mtu_size", "unknown")
        )

    async def async_disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    @callback
    def _on_notify(self, _handle: int, payload: bytearray) -> None:
        parsed = parse_frame(bytes(payload))
        if parsed is None:
            return
        self.data.update(parsed)
        self.async_set_updated_data(self.data)

    async def async_set_field(self, offset: int, value: int) -> None:
        """Send a 'set field' command, e.g. offset=13 (AC switch), value=1."""
        if not self.connected:
            await self.async_connect()
        assert self._client is not None
        frame = build_set_field_frame(offset, value)
        # response=True ("Write Request") gets rejected by this device with
        # ATT error 0x0E (Unlikely Error) even at a correctly raised MTU, so
        # despite the characteristic advertising the 'write' property, use
        # an unacknowledged write here instead.
        await self._client.write_gatt_char(CHAR_WRITE, frame, response=False)
        _LOGGER.debug("Sent EHOM set-field offset=%s value=%s frame=%s", offset, value, frame.hex())
