# EHOM / Loncin Power Station for Home Assistant

A local Bluetooth LE (no cloud) Home Assistant integration for EHOM
portable power stations that use the "Loncin" app (package
`com.loncin.portablepower`), such as the EHOM EP600. It talks to the
device directly over BLE from Home Assistant's own Bluetooth adapter(s),
reusing whatever passive/active Bluetooth proxy setup you already have.

The protocol was reverse engineered by decompiling the official Loncin
Android app (no traffic capture was available). **Reading device data
works reliably. Writing (turning outputs on/off, changing charge
limits) does not work reliably yet** - see [Known issues](#known-issues)
below. Contributions, especially a real BLE packet capture of a working
write from the official app, are very welcome.

## What you get

### Sensors (read-only, confirmed working)

- Battery (SOC %), input/output power (total, AC, DC), device
  temperature, remaining/charging time, charge status, work status,
  alarm code, AC charge power limit (300W/600W).

### Switches and selects (implemented, **not confirmed working** - see below)

- AC output, DC output (the app only exposes these two; USB-A/USB-C/12V
  DC/Wireless are read-only sub-outputs gated by the DC switch, not
  independently controllable).
- Charge upper limit (80-100%), discharge lower limit (0-20%).

## Installation

### HACS / Marketplace (custom repository)

This repository isn't in the default curated catalog. Add it as a
custom repository:

- **HACS:** HACS > Integrations > ⋮ > Custom repositories > add this
  repo URL, category "Integration".
- **Home Assistant Marketplace** (2026.x+): Settings > Marketplace >
  add this repo URL as a custom integration repository.

### Manual

Copy `custom_components/ehom_loncin` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Setup

Home Assistant should auto-discover the device over Bluetooth (it
advertises the service UUID below) and offer to set it up. If not,
add it manually via Settings > Devices & Services > Add Integration >
"EHOM / Loncin Power Station", and pick it from the list of nearby
Bluetooth devices.

The device only accepts one BLE connection at a time - close the
Loncin app on your phone/tablet (it holds the connection open) before
Home Assistant can connect.

## Protocol notes

Reverse engineered from `com.loncin.portablepower.bluetooth.{a,b,c}`
in the decompiled app (the generic BLE transport is shared with
`com.loncin.motorbluetooth`, Loncin's engine/generator product line).
Devices using the *other* Loncin product family (older EP1650/PEACE
models, package `com.loncin.tjehom`) use a different, hex-ASCII-based
protocol and are not supported here.

```
Service:  0000a002-0000-1000-8000-00805f9b34fb
Notify:   0000c305-0000-1000-8000-00805f9b34fb
Write:    0000c304-0000-1000-8000-00805f9b34fb
```

Frames are raw binary, 11-byte header + 1 type byte + payload, with a
CRC32 (`java.util.zip.CRC32`, same algorithm as `zlib.crc32`) over
`bytes[12 : 12 + payload_len - 1]`, stored big-endian in header bytes
`[4:8]`:

```
[0]      0x3F  (sentinel - okio's Utf8.REPLACEMENT_BYTE, '?')
[1]      0x3A  (':')
[2]      0x01
[3]      payload_len - 1
[4:8]    CRC32(bytes[12 : 12 + payload_len - 1]), big-endian
[8:11]   0x01 0x01 0x01
[11]     frame type
[12:]    payload
```

Incoming notify frames are dispatched purely on `byte[11]` (the frame
type); see `const.py` for the full field layout of types `0x01`
(battery/runtime), `0x02` (power flow) and `0x03` (output switches).

Outgoing "set a field" commands (frame type `0x32`) write
`byte[offset] = 1` (a presence flag) and `byte[offset+1] = value`, at
the same absolute offsets used by the matching read frame (e.g. offset
13 for the AC switch, matching `byte[13]` in a type-`0x03` read
frame). This is implemented in `coordinator.build_set_field_frame()`.

## Known issues

- **Writes are unreliable.** The exact command frame for "set a field"
  was derived from the app's `SendBluetoothData.l()` method, not from
  a captured working write, and is likely incomplete or subtly wrong:
  - With `response=True` ("Write Request"), the device rejects the
    frame with ATT error `0x0E` (Unlikely Error), even at a correctly
    negotiated MTU.
  - With `response=False` ("Write Command"), the device accepts the
    frame with no error, but does not act on it.
  - A single successful AC-on write *was* observed early on after
    fixing the sentinel byte, but has not been reproducible since -
    something about the command structure (or a required
    preceding/following command) is still missing.
- bleak's BlueZ backend does not raise the ATT MTU above the default 23
  bytes on its own for this device; `coordinator.py` works around this
  by calling the backend's private `_acquire_mtu()`, since bleak has no
  public API for it. This is fragile and may break on future bleak
  versions.
- The USB-A/USB-C/12V DC/Wireless outputs, screen timeout, device
  standby timeout, AC standby timeout, voice/buzzer toggle, and
  "Hyper Power" mode are not yet exposed as entities, though their
  frame types were identified in the app's code.

If you can capture real BLE traffic from the official app while
toggling a switch (e.g. with a rooted Android device's
`btsnoop_hci.log`, or a dedicated BLE sniffer), comparing it against
`coordinator.build_set_field_frame()`'s output for the same action
would very likely resolve this. Issues and PRs welcome.

## Disclaimer

Unofficial, reverse-engineered integration with no affiliation to
Loncin or EHOM. Use at your own risk.
