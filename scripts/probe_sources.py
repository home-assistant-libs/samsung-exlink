# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "samsung-exlink",
# ]
#
# [tool.uv.sources]
# samsung-exlink = { path = "..", editable = true }
# ///
"""Probe the TV's source map and report a Python dict you can paste back.

Use the printed mapping as the ``source_map=`` argument to ``SamsungTV(...)``
on subsequent runs, so you don't have to re-probe.
"""

from __future__ import annotations

import asyncio

from samsung_exlink import SamsungTV

SERIAL_URL = "esphome://192.168.1.29/?port_name=DB-9 Port"


async def main() -> None:
    tv = SamsungTV(SERIAL_URL)
    await tv.connect()
    try:
        print("Probing... this will switch inputs briefly.\n")
        mapping = await tv.probe_sources()

        print("=== Result ===\n")
        for source, byte in mapping.items():
            print(f"  {source.name:<10} -> 0x{byte:02x}")

        print("\nPaste this into your code:\n")
        print("    from samsung_exlink import InputSource, SamsungTV")
        print("    tv = SamsungTV(")
        print(f'        "{SERIAL_URL}",')
        print("        source_map={")
        for source, byte in mapping.items():
            print(f"            InputSource.{source.name}: 0x{byte:02x},")
        print("        },")
        print("    )")

        print("\nVerifying query_source_input()...")
        current = await tv.query_source_input()
        print(f"  current source: {current.name if current else 'unknown'}")
    finally:
        await tv.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
