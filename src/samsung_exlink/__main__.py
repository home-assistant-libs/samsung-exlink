"""CLI to control a Samsung TV over RS232.

Usage:
    python -m samsung_exlink PORT power-on
    python -m samsung_exlink PORT power-off
    python -m samsung_exlink PORT volume 25
    python -m samsung_exlink PORT mute
    python -m samsung_exlink PORT source HDMI1
    python -m samsung_exlink PORT key KEY_MENU
    python -m samsung_exlink PORT raw 0d 00 00 1a
    python -m samsung_exlink PORT status        # query and print all TV state
    python -m samsung_exlink PORT listen        # passive: print incoming frames
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import (
    MODELS,
    CommandRejected,
    InputSource,
    Key,
    PowerState,
    SamsungTV,
)


async def _query_safe(coro):
    """Run a query coroutine, returning None on timeout/error."""
    try:
        return await coro
    except (TimeoutError, Exception) as err:
        return f"<error: {type(err).__name__}: {err}>"


def _format_channel(channel: tuple[int, int, int], on_tv_input: bool) -> str:
    """Format the (primary, major, minor) channel triple.

    The TV reports broadcast channel info as three bytes: the primary
    channel number, then ATSC major / minor sub-channels (``0xFF`` = none).
    On HDMI / AV / etc. the bytes are stale residue from the last broadcast
    input and aren't meaningful.
    """
    primary, major, minor = channel
    if not on_tv_input:
        return f"n/a (last seen: {primary}-{major}-{minor})"
    if major == 0xFF and minor == 0xFF:
        return str(primary)
    if minor == 0xFF:
        return f"{primary}.{major}"
    return f"{primary}.{major}.{minor}"


async def _print_status(tv: SamsungTV) -> None:
    """Query every documented status category and print it."""
    power = await _query_safe(tv.query_power())
    volume = await _query_safe(tv.query_volume())
    mute = await _query_safe(tv.query_mute())
    raw_source = await _query_safe(tv.query_source())
    channel = await _query_safe(tv.query_channel())

    if isinstance(power, PowerState):
        power_str = f"{power.name} (0x{power.value:02x})"
    else:
        power_str = str(power)

    if isinstance(mute, bool):
        mute_str = "ON" if mute else "off"
    else:
        mute_str = str(mute)

    on_tv_input = False
    has_map = bool(tv.source_map)
    if isinstance(raw_source, int):
        named = next(
            (s.name for s, b in tv.source_map.items() if b == raw_source),
            None,
        )
        source_str = f"0x{raw_source:02x}" + (f"  ({named})" if named else "")
        on_tv_input = named == "TV"
    else:
        source_str = str(raw_source)

    if isinstance(channel, tuple):
        channel_str = _format_channel(channel, on_tv_input)
    else:
        channel_str = str(channel)

    print()
    print("=== TV Status ===")
    print(f"  Power:    {power_str}")
    volume_str = f"{volume}/100" if isinstance(volume, int) else str(volume)
    print(f"  Volume:   {volume_str}")
    print(f"  Mute:     {mute_str}")
    print(f"  Source:   {source_str}")
    print(f"  Channel:  {channel_str}")
    print()

    if not has_map:
        print(
            "Hint: source byte not translated to a name. "
            f"Pass --model to use a known mapping "
            f"(one of: {', '.join(sorted(MODELS))}), "
            "or run scripts/probe_sources.py to derive one for your TV."
        )
        print()


async def _run_command(tv: SamsungTV, args: argparse.Namespace) -> None:
    cmd = args.command
    if cmd == "power-on":
        await tv.power_on()
    elif cmd == "power-off":
        await tv.power_off()
    elif cmd == "volume":
        await tv.set_volume(args.level)
    elif cmd == "volume-up":
        await tv.volume_up()
    elif cmd == "volume-down":
        await tv.volume_down()
    elif cmd == "mute":
        await tv.mute()
    elif cmd == "channel-up":
        await tv.channel_up()
    elif cmd == "channel-down":
        await tv.channel_down()
    elif cmd == "source":
        await tv.select_input_source(InputSource[args.source])
    elif cmd == "key":
        try:
            key = Key[args.key]
        except KeyError:
            print(
                f"Unknown key: {args.key}. Available: "
                + ", ".join(k.name for k in Key),
                file=sys.stderr,
            )
            sys.exit(2)
        await tv.send_key(key)
    elif cmd == "raw":
        cmd1, cmd2, cmd3, value = (int(x, 16) for x in args.bytes)
        response = await tv.send_raw(cmd1, cmd2, cmd3, value)
        print(f"Response: {response.hex(' ')}")
    elif cmd == "status":
        await _print_status(tv)
    elif cmd == "listen":
        print("Listening for frames (Ctrl-C to stop)...")
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
    else:  # pragma: no cover
        raise AssertionError(f"Unhandled command: {cmd}")


async def _run(port: str, args: argparse.Namespace) -> None:
    model = MODELS[args.model] if args.model else None
    tv = SamsungTV(port, model=model)

    print(f"Connecting to {port}...")
    try:
        await tv.connect()
    except Exception as err:
        print(f"Error connecting: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        await _run_command(tv, args)
        print("OK")
    except CommandRejected as err:
        print(f"Command rejected: {err}", file=sys.stderr)
        sys.exit(2)
    except TimeoutError:
        print(
            "Timed out waiting for response (TV may be off or not connected)",
            file=sys.stderr,
        )
        sys.exit(2)
    finally:
        await tv.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Control a Samsung consumer TV over RS232",
    )
    parser.add_argument(
        "port",
        help="Serial port (e.g. /dev/ttyUSB0 or esphome://host/?port_name=TTL)",
    )
    parser.add_argument(
        "--model",
        default=None,
        choices=sorted(MODELS),
        help="Pre-populate the source map with a known TV-generation mapping. "
        "Without it, the source byte is shown but not named.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("power-on", help="Turn the TV on")
    sub.add_parser("power-off", help="Turn the TV off")

    p_volume = sub.add_parser("volume", help="Set volume directly (0-100)")
    p_volume.add_argument("level", type=int)

    sub.add_parser("volume-up", help="Volume up one step")
    sub.add_parser("volume-down", help="Volume down one step")
    sub.add_parser("mute", help="Toggle mute")
    sub.add_parser("channel-up", help="Channel up")
    sub.add_parser("channel-down", help="Channel down")

    p_source = sub.add_parser("source", help="Select an input source")
    p_source.add_argument(
        "source",
        choices=[s.name for s in InputSource],
    )

    p_key = sub.add_parser("key", help="Send a remote-control key")
    p_key.add_argument("key", help="Key name (e.g. KEY_MENU)")

    p_raw = sub.add_parser(
        "raw", help="Send a raw 4-byte command (cmd1 cmd2 cmd3 value)"
    )
    p_raw.add_argument("bytes", nargs=4, help="four hex bytes, e.g. 0d 00 00 1a")

    sub.add_parser("status", help="Query and print all TV state")
    sub.add_parser("listen", help="Open the port and print incoming frames")

    args = parser.parse_args()
    asyncio.run(_run(args.port, args))


if __name__ == "__main__":
    main()
