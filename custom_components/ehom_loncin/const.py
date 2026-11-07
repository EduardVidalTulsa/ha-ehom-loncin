"""Constants for the EHOM / Loncin EP600 portable power station integration.

Protocol reverse engineered from the official "Loncin" Android app
(package com.loncin.portablepower, classes
com.loncin.portablepower.bluetooth.{a,b,c} = BluetoothData /
ReceiveBluetoothData / SendBluetoothData). The EP600 (and siblings other
than EP350) use the generic com.loncin.motorbluetooth BLE transport:

  Service:  0000a002-0000-1000-8000-00805f9b34fb
  Notify:   0000c305-0000-1000-8000-00805f9b34fb
  Write:    0000c304-0000-1000-8000-00805f9b34fb

Frames are raw binary (not hex-ASCII), 11-byte fixed header + 1 type byte
+ payload, with a CRC32 (java.util.zip.CRC32 / zlib crc32 - same
algorithm) over payload bytes [12:12+len-1], stored big-endian in header
bytes [4:8]:

  [0]      0xEF (sentinel, Utf8.REPLACEMENT_BYTE)
  [1]      0x3A (':')
  [2]      0x01
  [3]      payload_len - 1
  [4:8]    CRC32(bytes[12 : 12+payload_len-1]), big-endian
  [8:11]   0x01 0x01 0x01
  [11]     frame type (see FIELD_HANDLERS / CMD_* below)
  [12:]    payload

Incoming notify frames are dispatched purely on byte[11] (the frame
type); each type updates a different subset of fields on the shared
DeviceInfoEntity-equivalent state. EHOM 350 (distinct from EP350) widely
sold under "Loncin" uses this same EP600-family protocol.
"""

from __future__ import annotations

SERVICE_UUID = "0000a002-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000c305-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "0000c304-0000-1000-8000-00805f9b34fb"

DOMAIN = "ehom_loncin"

FRAME_SENTINEL = 0x3F

# --- Receive: frame type (byte[11]) -> fields it carries -------------
# Offsets below are absolute indices into the raw frame bytes.

# type 0x01: battery / runtime status
FIELDS_01 = {
    "soc": (12, 1),  # unsigned byte, %
    "charge_left_time": (13, 2),  # minutes
    "residue_time": (15, 2),  # minutes
    "device_temperature": (17, 1),  # signed byte, degC
    "fan_status": (18, 1),
    "run_time": (19, 2),
    "light_mode": (21, 1),
    "light": (22, 1),
    "quiet_mode": (23, 1),  # bool
    "button_sound": (24, 1),  # bool
    "x_boost": (25, 1),  # bool
    "add_package_connect_status": (26, 1),
    "work_status": (27, 1),
    "work_status_switch_reason": (28, 1),
    "alarm": (29, 1),
    "charge_status": (30, 1),
}

# type 0x02: power flow
FIELDS_02 = {
    "dc_total_output_power": (12, 2),
    "ac_total_output_power": (14, 2),
    "output_power": (16, 2),
    "input_power": (18, 2),
    "ac_charge_mode": (20, 2),
    "dc_charge_mode": (22, 1),
    "dc_charge_type": (23, 1),
    "charge_upper": (24, 1),  # %
    "discharge_lower": (25, 1),  # %
    "ac_total_input_power": (26, 2),
    "dc_total_input_power": (28, 2),
}

# type 0x03: output switches
FIELDS_03 = {
    "dc_switch": (12, 1),  # bool
    "ac_switch": (13, 1),  # bool
    "usb_switch": (14, 1),  # bool
    "shutdown_time_set": (15, 2),
    "rest_screen_time_set": (17, 2),
    "dc_output_definite_time": (19, 2),
    "ac_output_definite_time": (21, 2),
    "usb_output_definite_time": (23, 2),
}

FRAME_FIELD_MAP: dict[int, dict[str, tuple[int, int]]] = {
    0x01: FIELDS_01,
    0x02: FIELDS_02,
    0x03: FIELDS_03,
}

BOOL_FIELDS = {
    "quiet_mode",
    "button_sound",
    "x_boost",
    "dc_switch",
    "ac_switch",
    "usb_switch",
}

# --- Write: "set field" commands ---------------------------------------
# Confirmed 2026-11-07 from a real Android btsnoop_hci.log capture of the
# official Loncin app toggling AC/DC and the light mode. Each writable
# "page" has its own frame type and its own compact field layout - this
# is NOT the single uniform command the field offsets were originally
# guessed to be; every (offset, value) pair below is byte[offset] = 1
# (field-present flag), byte[offset + 1] = value, exactly as before, but
# the command byte and offsets differ per page:
#
#   type 0x33 (output switches, mirrors read type 0x03): total frame
#   length 35 bytes. dc_switch flag at byte 12, ac_switch flag at byte 14.
#   type 0x31 (light mode, mirrors read type 0x01): total frame length
#   28 bytes. light flag at byte 16.
#
# The write characteristic accepts this as a BLE "Write Request" (with
# response) once the MTU is correctly raised - this matches the app
# exactly and is more reliable than the previously-assumed "Write
# Command" workaround.
CMD_SET_OUTPUT = 0x33
FRAME_LEN_OUTPUT = 35
OFFSET_DC_SWITCH = 12
OFFSET_AC_SWITCH = 14

CMD_SET_LIGHT = 0x31
FRAME_LEN_LIGHT = 28
OFFSET_LIGHT = 16

LIGHT_MODES = {"off": 0, "low": 1, "high": 2, "sos": 3}

# type 0x32 (mirrors read type 0x02: power flow / charge limits) has NOT
# been confirmed against a real capture - the offsets below are carried
# over from the original (also unverified) guess and are kept only so
# charge_upper/discharge_lower don't regress further; frame_len was
# bumped from the old guess of 25 to fit offset 25 + 1 without going out
# of bounds. Treat this command as experimental until it's captured.
CMD_SET_POWER = 0x32
FRAME_LEN_POWER = 27
OFFSET_CHARGE_LIMIT = 24
OFFSET_DISCHARGE_LIMIT = 25

CHARGE_LIMIT_OPTIONS = [80, 85, 90, 95, 100]
DISCHARGE_LIMIT_OPTIONS = [0, 5, 10, 15, 20]
