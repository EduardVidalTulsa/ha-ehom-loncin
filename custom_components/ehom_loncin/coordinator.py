"""BLE connection and protocol handling for the EHOM / Loncin EP600 power station."""

from __future__ import annotations

import asyncio
import logging
import zlib

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BOOL_FIELDS,
    CHAR_NOTIFY,
    CHAR_WRITE,
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


def build_set_field_frame(cmd_type: int, total_len: int, offset: int, value: int) -> bytes:
    """Build a 'set field' command frame for the given write page.

    Confirmed against a real btsnoop_hci.log capture of the official app
    (2026-11-07): the CRC32 covers bytes[12 : 12 + payload_len - 1], the
    byte right after that is a fixed 0x4E marker, and the frame ends with
    a fixed 0x4B terminator - neither of which is covered by the CRC.
    """
    payload_len = total_len - 13
    frame = bytearray(total_len)
    frame[0] = FRAME_SENTINEL
    frame[1] = 0x3A
    frame[2] = 0x01
    frame[3] = payload_len - 1
    frame[8] = 1
    frame[9] = 1
    frame[10] = 1
    frame[11] = cmd_type
    frame[offset] = 1
    frame[offset + 1] = value & 0xFF
    crc = zlib.crc32(bytes(frame[12 : 12 + payload_len - 1])) & 0xFFFFFFFF
    frame[4] = (crc >> 24) & 0xFF
    frame[5] = (crc >> 16) & 0xFF
    frame[6] = (crc >> 8) & 0xFF
    frame[7] = crc & 0xFF
    frame[12 + payload_len - 1] = 0x4E
    frame[-1] = 0x4B
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

    async def async_set_field(self, cmd_type: int, total_len: int, offset: int, value: int) -> None:
        """Send a 'set field' command, e.g. the AC switch on the output page."""
        frame = build_set_field_frame(cmd_type, total_len, offset, value)
        # Write Request (response=True) is what the official app uses, and
        # it works once the frame content is correct and the MTU has been
        # raised above the BlueZ default (see async_connect). In practice
        # the device still occasionally rejects an otherwise-correct write
        # with ATT error 0x0E ("Unlikely Error") shortly after a fresh
        # connection/MTU exchange - the official app has the same issue
        # (hence it keeps a long-lived connection and a heartbeat instead
        # of reconnecting per command). Retry a few times before giving up.
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                if not self.connected:
                    await self.async_connect()
                assert self._client is not None
                await self._client.write_gatt_char(CHAR_WRITE, frame, response=True)
            except BleakError as err:
                last_error = err
                self._client = None
                _LOGGER.debug(
                    "EHOM set-field attempt %s failed (%s), retrying", attempt + 1, err
                )
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            _LOGGER.debug(
                "Sent EHOM set-field cmd=%#x offset=%s value=%s frame=%s (attempt %s)",
                cmd_type,
                offset,
                value,
                frame.hex(),
                attempt + 1,
            )
            return
        assert last_error is not None
        raise last_error
