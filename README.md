# EHOM / Loncin Power Station for Home Assistant

A local Bluetooth LE (no cloud) Home Assistant integration for EHOM
portable power stations that use the "Loncin" app (package
`com.loncin.portablepower`), such as the EHOM EP600. It talks to the
device directly over BLE from Home Assistant's own Bluetooth adapter(s),
reusing whatever passive/active Bluetooth proxy setup you already have.

The protocol was first reverse engineered by decompiling the official
Loncin Android app, then corrected and confirmed against a real
`btsnoop_hci.log` capture of that app toggling AC/DC and the light.
**Reading device data and the AC/DC output switches are confirmed
working.** The device's BLE write occasionally rejects an
otherwise-correct frame with ATT error `0x0E` ("Unlikely Error") right
after a fresh connection - `coordinator.py` retries a few times, which
is enough in practice. See [Known issues](#known-issues) for what's
still unconfirmed.

## What you get

### Sensors (read-only, confirmed working)

- Battery (SOC %), input/output power (total, AC, DC), device
  temperature, remaining/charging time, charge status, work status,
  alarm code, AC charge power limit (300W/600W).

### Switches and selects

- AC output, DC output (**confirmed working**; the app only exposes
  these two - USB-A/USB-C/12V DC/Wireless are read-only sub-outputs
  gated by the DC switch, not independently controllable).
- Light: off / low / high / SOS (**confirmed working**, new).
- Charge upper limit (80-100%), discharge lower limit (0-20%)
  (**unconfirmed** - the write command for this field group hasn't
  been captured yet, see Known issues).

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

Outgoing "set a field" commands do **not** share one command type or
one offset layout with the read frames - each writable page has its
own frame type and its own compact `(flag, value)` layout, confirmed
from a real capture (2026-11-07) of the official app:

- Type `0x33` (output switches, mirrors read type `0x03`): 35-byte
  frame, `dc_switch` flag at byte 12, `ac_switch` flag at byte 14.
- Type `0x31` (light mode, mirrors read type `0x01`): 28-byte frame,
  light flag at byte 16 (value 0=off, 1=low, 2=high, 3=SOS).
- Type `0x32` (power/charge limits, mirrors read type `0x02`): **not
  yet captured** - `const.py`'s offsets for this one are still a guess
  carried over from before the real capture, so `charge_upper` /
  `discharge_lower` should be treated as experimental.

In every case, `byte[offset] = 1` is a presence flag and
`byte[offset + 1] = value`. The CRC32 covers `bytes[12 : 12 +
payload_len - 1]` only; right after that comes a fixed `0x4E` marker
byte, then the frame ends with a fixed `0x4B` terminator - neither of
which is covered by the CRC. This is implemented in
`coordinator.build_set_field_frame()`.

## Known issues

- **Charge/discharge limit (and charge-power-limit) writes are still
  unconfirmed.** Type `0x32`'s field layout hasn't been captured from
  real traffic yet - if you can grab a `btsnoop_hci.log` (Android
  Developer options > Enable Bluetooth HCI snoop log) while changing
  one of these in the official app, that would nail down the last
  piece. See the AC/DC and light sections above for the method that
  worked.
- The device occasionally rejects an otherwise byte-correct write with
  ATT error `0x0E` ("Unlikely Error") shortly after a fresh
  connection/MTU exchange - `async_set_field()` retries a few times
  with a short backoff, which has been enough in testing, but a
  long-lived connection (like the official app keeps, with a ~700ms
  heartbeat) would likely be even more reliable than reconnecting per
  command.
- bleak's BlueZ backend does not raise the ATT MTU above the default 23
  bytes on its own for this device; `coordinator.py` works around this
  by calling the backend's private `_acquire_mtu()`, since bleak has no
  public API for it. This is fragile and may break on future bleak
  versions.
- The USB-A/USB-C/12V DC/Wireless outputs, screen timeout, device
  standby timeout, AC standby timeout, voice/buzzer toggle, and
  "Hyper Power" mode are not yet exposed as entities, though their
  frame types were identified in the app's code.
- Device name and charge-power-limit (100-600W) settings from the
  app's device-settings screen haven't been captured or wired up yet.

Issues and PRs welcome.

## Capturing your own traffic (if this doesn't work for your device)

The offsets and command bytes above were confirmed on one specific
device (an EHOM EP600, app version as of 2026-11) over about an hour of
trial and error. If your writes fail, it's quite possible your
device's firmware or app version numbers fields differently - the
*method* below is more reusable than the exact byte values.

What **didn't** work well: an external nRF52840 BLE sniffer (the
`nrfutil ble-sniffer` / Wireshark route). It's the "proper" way to
sniff BLE on paper, but following a connection reliably requires the
sniffer to catch the exact `CONNECT_IND` packet when the central
initiates the link, which is a narrow timing window - most of an
evening went into fighting with that for comparatively little payoff.

What **did** work, in under 20 minutes once set up: Android's own
**Bluetooth HCI snoop log**, since you already have the app running on
a phone/tablet anyway.

1. On the Android device running the Loncin app: Settings > About
   phone > tap "Build number" 7 times to unlock Developer options.
2. Settings > Developer options > "Enable Bluetooth HCI snoop log" >
   choose **Enabled** (not "Enabled Filtered" - you want everything).
3. Toggle Bluetooth off and on (`adb shell svc bluetooth disable` then
   `enable`, or just the Quick Settings tile) so the logger actually
   starts - the setting doesn't apply to an already-running Bluetooth
   stack.
4. Open the Loncin app, connect to the device, and do *one* clean
   action at a time (e.g. toggle AC off, wait a couple of seconds,
   toggle it back on) - the cleaner the action sequence, the easier it
   is to spot the matching frame afterwards.
5. Pull the log. The file lives at `/data/log/bt/btsnoop_hci.log` (or
   `/data/misc/bluetooth/logs/btsnoop_hci.log` on some versions), which
   `adb shell` can't read directly on a non-rooted device - instead run
   `adb bugreport out.zip` and extract
   `FS/data/log/bt/btsnoop_hci.log` from the resulting zip.
6. Open it with `tshark` or Wireshark and filter for the write
   characteristic's ATT writes:
   `tshark -r btsnoop_hci.log -Y "btatt.opcode == 0x12 || btatt.opcode == 0x52" -T fields -e frame.time_relative -e btatt.handle -e btatt.value`
7. Match the timestamps to what you did in step 4. `byte[11]` is the
   frame type, `byte[3] + 1` is the payload length, and from there
   it's the same `(flag, value)` layout described above - just find
   which byte flips between your "before" and "after" captures.

If you do this for the charge-power-limit or charge/discharge-limit
sliders (the ones this integration doesn't control yet), please open
an issue or PR with the captured bytes - see Known issues above.

## Disclaimer

Unofficial, reverse-engineered integration with no affiliation to
Loncin or EHOM. Use at your own risk.
