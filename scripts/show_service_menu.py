# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "aioesphomeapi",
#     "infrared-protocols",
# ]
# ///
"""Demo: send Samsung TV IR commands via ESPHome IR proxy."""

import asyncio

from aioesphomeapi import APIClient
from aioesphomeapi.model import InfraredInfo
from infrared_protocols.codes.samsung.tv import SamsungTVCode

DEVICE_HOST = "192.168.1.155"
DEVICE_PORT = 6053

SEQUENCE = [
    SamsungTVCode.MUTE,
    SamsungTVCode.NUM_1,
    SamsungTVCode.NUM_8,
    SamsungTVCode.NUM_2,
    SamsungTVCode.POWER,
]


async def main() -> None:
    client = APIClient(DEVICE_HOST, DEVICE_PORT, password=None)
    await client.connect()

    try:
        entities, _ = await client.list_entities_services()
        ir_entities = [e for e in entities if isinstance(e, InfraredInfo)]
        if not ir_entities:
            print("No IR transmitter found on device")
            return
        ir_key = ir_entities[0].key
        print(f"Using IR transmitter: {ir_entities[0].name} (key={ir_key})")

        for code in SEQUENCE:
            cmd = code.to_command()
            timings = cmd.get_raw_timings()
            print(f"Sending {code.name} (0x{code.value:02X}): {len(timings)} timings")
            client.infrared_rf_transmit_raw_timings(
                key=ir_key,
                carrier_frequency=cmd.modulation,
                timings=timings,
            )
            await asyncio.sleep(0.5)
    finally:
        await client.disconnect()


asyncio.run(main())
