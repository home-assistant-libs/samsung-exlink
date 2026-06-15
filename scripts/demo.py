# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "samsung-exlink",
# ]
#
# [tool.uv.sources]
# samsung-exlink = { path = "..", editable = true }
# ///
"""End-to-end demo of samsung-exlink.

Connects to the Samsung Frame TV via the ESPHome RS-232 proxy, reads its
state via the cmd1=0xF0 query interface, then drives a few visible
controls and reads state again to confirm the change took effect.
"""

from __future__ import annotations

import asyncio

from samsung_exlink import (
    Key,
    PowerState,
    SamsungTV,
)

SERIAL_URL = "esphome://192.168.1.29/?port_name=DB-9 Port"


def fmt(label: str, value: object) -> str:
    return f"  {label:<10} {value}"


async def show_state(tv: SamsungTV) -> None:
    power = await tv.query_power()
    volume = await tv.query_volume()
    muted = await tv.query_mute()
    source = await tv.query_source()
    channel = await tv.query_channel()
    print(fmt("power",   f"{power.name} (0x{power.value:02x})"))
    print(fmt("volume",  f"{volume}/100"))
    print(fmt("mute",    "ON" if muted else "off"))
    print(fmt("source",  f"0x{source:02x}"))
    print(fmt("channel", "-".join(str(b) for b in channel)))


async def main() -> None:
    tv = SamsungTV(SERIAL_URL)
    print(f"Connecting to {SERIAL_URL}")
    await tv.connect()

    try:
        print("\n--- Initial state ---")
        await show_state(tv)

        if (await tv.query_power()) is not PowerState.ON:
            print("\nTV not on; powering on for the demo")
            await tv.power_on()
            await asyncio.sleep(2.0)

        print("\n--- Setting volume to 15 ---")
        await tv.set_volume(15)
        await asyncio.sleep(0.5)
        print(fmt("volume", f"{await tv.query_volume()}/100"))

        print("\n--- Mute toggle, twice ---")
        await tv.mute()
        await asyncio.sleep(0.5)
        print(fmt("mute (1)", "ON" if await tv.query_mute() else "off"))
        await tv.mute()
        await asyncio.sleep(0.5)
        print(fmt("mute (2)", "ON" if await tv.query_mute() else "off"))

        print("\n--- Pressing INFO twice (visible OSD banner) ---")
        await tv.send_key(Key.KEY_INFO)
        await asyncio.sleep(1.0)
        await tv.send_key(Key.KEY_INFO)

        print("\n--- Final state ---")
        await show_state(tv)
    finally:
        await tv.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
