"""Connect to the ESPHome serial proxy and print everything from the TV."""

from __future__ import annotations

import asyncio
import sys

from serialx import open_serial_connection

URL = "esphome://192.168.1.29/?port_name=TTL"


async def main() -> None:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    reader, writer = await open_serial_connection(url=URL, baudrate=9600)
    print(f"Connected to {URL}; reading for {duration:.1f}s")
    try:
        try:
            async with asyncio.timeout(duration):
                while True:
                    data = await reader.read(64)
                    if not data:
                        print("EOF")
                        break
                    print(f"raw={data!r} hex={data.hex(' ')}")
        except TimeoutError:
            pass
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
