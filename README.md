# samsung-exlink

Async Python library to control Samsung consumer TVs (Frame, Q-series, 8000-series, etc.) over their RS232 serial connection -- which Samsung markets as **ExLink** (also written EX-Link / EXT Link) -- built on [serialx](https://github.com/puddly/serialx).

"ExLink" and "RS232" refer to the same thing here: the TV's serial control port. This library speaks that protocol; it does not use the network/WiFi APIs.

## Installation

```bash
pip install samsung-exlink
```

Requires Python 3.12+.

## Hardware

Samsung consumer TVs expose RS232 either via:

- A native 3.5 mm "ExLink" jack (Q70 and above) -- plug in and go.
  - 3.5 mm pin-out: tip = TV TX (RX into your controller), ring = TV RX, sleeve = GND.
- A USB port via the proprietary Samsung USB-to-ExLink dongle (8000 / Q60).
  - The TV's service menu (Mute -> 1 -> 8 -> 2 -> Power on the IR remote) must
    have **EXT Link Support** and **USB Serial** enabled.

The serial link is 9600 8N1.

## Quick start

```python
import asyncio
from samsung_exlink import SamsungTV, InputSource, Key, PictureMode

async def main():
    tv = SamsungTV("/dev/ttyUSB0")
    await tv.connect()
    try:
        await tv.power_on()
        await tv.set_volume(25)
        await tv.select_input_source(InputSource.HDMI1)
        await tv.set_picture_mode(PictureMode.MOVIE)
        await tv.send_key(Key.KEY_MENU)
    finally:
        await tv.disconnect()

asyncio.run(main())
```

The constructor also accepts an `esphome://host/?port_name=NAME` URL for use
with an ESPHome UART proxy.

## CLI

A built-in CLI lets you quickly test your connection:

```bash
python -m samsung_exlink /dev/ttyUSB0 power-on
python -m samsung_exlink /dev/ttyUSB0 power-off
python -m samsung_exlink /dev/ttyUSB0 volume 25
python -m samsung_exlink /dev/ttyUSB0 volume-up
python -m samsung_exlink /dev/ttyUSB0 volume-down
python -m samsung_exlink /dev/ttyUSB0 mute
python -m samsung_exlink /dev/ttyUSB0 channel-up
python -m samsung_exlink /dev/ttyUSB0 channel-down
python -m samsung_exlink /dev/ttyUSB0 source HDMI1
python -m samsung_exlink /dev/ttyUSB0 key KEY_MENU
python -m samsung_exlink /dev/ttyUSB0 raw 0d 00 00 1a   # MENU via raw command
python -m samsung_exlink /dev/ttyUSB0 status           # query power/volume/mute/source/channel
python -m samsung_exlink /dev/ttyUSB0 listen           # passively log frames
```

The `status` command queries the TV directly. To translate the raw source
byte into a named input, pass a known generation with `--model` (one of
`frame_2022`, `h_series_2016`):

```bash
python -m samsung_exlink --model frame_2022 /dev/ttyUSB0 status
```

## Protocol

Samsung consumer TVs use a fixed 7-byte binary frame:

```
08 22 [cmd1] [cmd2] [cmd3] [value] [checksum]
```

- `08 22` is the fixed header.
- `cmd1`, `cmd2`, `cmd3`, `value` form the command (see the protocol PDF
  bundled with this repo).
- `checksum = (256 - sum(bytes 0..5)) & 0xFF`.

The TV replies with a 3-byte response: `03 0C F1` for ACK, `03 0C FF` for
NACK. Most commands are fire-and-forget, so the library also tracks state
from what it sends. A subset of state (power, volume, mute, channel, source)
can additionally be read back with a `cmd1=0xF0` status query -- the TV
answers with `03 0C F5` plus a 10-byte payload. See
[State tracking](#state-tracking) below.

### Examples

| Operation        | Frame                               |
|------------------|-------------------------------------|
| Power off        | `08 22 00 00 00 01 D5`              |
| Power on         | `08 22 00 00 00 02 D4`              |
| Volume = 25      | `08 22 01 00 00 19 BC`              |
| Mute toggle      | `08 22 02 00 00 00 D4`              |
| Source: HDMI1    | `08 22 0A 00 05 00 C7`              |
| Source: TV       | `08 22 0A 00 00 00 CC`              |
| Key: MENU        | `08 22 0D 00 00 1A AF`              |

## Features

### State tracking

```python
state = tv.state
state.power          # bool | None  (None = unknown)
state.volume         # int | None   (0-100)
state.mute           # bool | None
state.input_source   # InputSource | None
state.picture_mode   # PictureMode | None
state.sound_mode     # SoundMode | None
```

Fields are populated as commands succeed, and also refreshed by the `query_*`
methods below. Power state is unknown after connect; call `power_on()` /
`power_off()`, or `query_power()` to read it from the TV.

### Status queries

Some TVs answer a small set of status queries directly:

```python
await tv.query_power()          # PowerState.ON / STANDBY / OFF
await tv.query_volume()         # 0-100
await tv.query_mute()           # bool
await tv.query_channel()        # (major, mid, minor)
await tv.query_source()         # raw source byte (generation-specific)
await tv.query_source_input()   # InputSource | None (needs a source map)
```

Each query updates `tv.state` and returns the value. The byte returned by
`query_source()` differs by TV generation, so mapping it back to an
`InputSource` needs a source map. Supply a known one via the constructor:

```python
from samsung_exlink import SamsungTV, MODELS

tv = SamsungTV("/dev/ttyUSB0", model=MODELS["frame_2022"])
```

or discover it for your TV once with `await tv.probe_sources()` (which
cycles every input and records the byte each reports) and pass the returned
mapping back as `source_map=...` on future runs. Queries raise `TimeoutError`
on TVs/firmwares that don't support them.

### Event subscription

```python
def on_state_change(state):
    if state is None:
        print("Disconnected")
        return
    print(f"Volume: {state.volume}, Source: {state.input_source}")

unsubscribe = tv.subscribe(on_state_change)
```

The callback is called with a `TVState` snapshot on each change, or `None`
when the connection is torn down.

### Raw access

```python
response = await tv.send_raw(0x0d, 0x00, 0x00, 0x1A)  # KEY_MENU
# response is the 3-byte reply (e.g. b"\x03\x0c\xf1")
```

`send_raw` returns the reply without raising on NACK, for diagnostics.

## Available commands

First-class helpers cover power (`power_on`/`power_off`/`power_toggle`),
volume (`set_volume`/`volume_up`/`volume_down`), `mute`, channels
(`channel_up`/`channel_down`), `select_input_source`, `set_picture_mode`,
`set_sound_mode`, and the Frame/Anynet+ toggles `set_art_mode`,
`set_ambient_mode`, and `set_hdmi_cec`.

The `Key` enum mirrors the Samsung remote-control key map and includes
power, source, navigation, transport, color, and number keys. The
`InputSource` enum covers TV, AV1-3, S-Video1-3, Component1-3, PC1-3,
HDMI1-4, DVI1-3, and RVU.

For commands not yet wrapped (e.g. white-balance, color space, screen
adjustments), use `send_raw()` with the values from the protocol PDF
(`docs/Samsung-RS232-Control.pdf`).

## License

MIT
