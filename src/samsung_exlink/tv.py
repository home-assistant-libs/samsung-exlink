"""Samsung TV controller for samsung_exlink."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import serialx

from .const import (
    ACK_RESPONSE,
    BAUD_RATE,
    COMMAND_TIMEOUT,
    FRAME_LENGTH,
    HEADER,
    MAX_VOLUME,
    NACK_RESPONSE,
    QUERY_DATA_FOLLOWS,
    QUERY_PAYLOAD_LENGTH,
    RESPONSE_LENGTH,
    InputSource,
    Key,
    PictureMode,
    PowerCommand,
    PowerState,
    QueryCategory,
    SoundMode,
)
from .protocol import (
    PendingResponse,
    QueryResponse,
    build_frame,
    is_ack,
    is_nack,
    parse_frame,
    parse_query_payload,
)
from .state import TVState

if TYPE_CHECKING:
    from .models import TVModel

_LOGGER = logging.getLogger(__name__)


StateCallback = Callable[[TVState | None], None]


class SamsungTVError(Exception):
    """Base error for samsung_exlink."""


class CommandRejected(SamsungTVError):
    """Raised when the TV explicitly rejects a command (NACK 03 0C FF)."""


class SamsungTV:
    """Async controller for a Samsung consumer TV over RS232.

    The TV uses a binary protocol: each 7-byte command frame is acknowledged
    with a 3-byte response (``03 0C F1``). Power, volume, mute, channel, and
    source can also be read back with the ``query_*`` methods. This class
    tracks state from both the commands it sends and the queries it makes.
    """

    def __init__(
        self,
        port: str,
        *,
        source_map: dict[InputSource, int] | None = None,
        model: TVModel | None = None,
    ) -> None:
        self._port = port
        self._model = model
        self._reader: asyncio.StreamReader | None = None
        self._writer: serialx.SerialStreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._state = TVState()
        self._subscribers: list[StateCallback] = []
        self._write_lock = asyncio.Lock()
        self._connected = False
        # Only one outstanding command at a time; protected by _write_lock.
        self._pending: PendingResponse | None = None
        self._pending_expects_query: bool = False
        # Mapping of InputSource -> source byte returned by query_source().
        # Pre-populate from ``model`` and/or ``source_map`` to skip
        # probe_sources() on subsequent runs.
        # ``source_map`` takes precedence over ``model.source_map`` for any
        # overlapping keys.
        merged: dict[InputSource, int] = {}
        if model is not None:
            merged.update(model.source_map)
        if source_map:
            merged.update(source_map)
        self._source_map: dict[InputSource, int] = merged

    @property
    def state(self) -> TVState:
        """Return a copy of the current state."""
        return self._state.copy()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def power(self) -> bool | None:
        """Return the last known power state, or None if unknown."""
        return self._state.power

    @property
    def source_map(self) -> dict[InputSource, int]:
        """Return a copy of the current ``InputSource -> source byte`` map."""
        return dict(self._source_map)

    @property
    def model(self) -> TVModel | None:
        """Return the configured TV model, if any."""
        return self._model

    def subscribe(self, callback: StateCallback) -> Callable[[], None]:
        """Subscribe to state changes. Returns an unsubscribe function."""
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)

    async def connect(self) -> None:
        """Open the serial connection."""
        self._reader, self._writer = await serialx.open_serial_connection(
            self._port,
            baudrate=BAUD_RATE,
        )
        self._connected = True
        self._read_task = asyncio.create_task(self._read_loop())
        _LOGGER.info("Connected to Samsung TV on %s", self._port)

    async def disconnect(self) -> None:
        """Close the serial connection."""
        await self._teardown()
        _LOGGER.info("Disconnected from Samsung TV")

    # -- High-level commands --

    async def power_on(self) -> None:
        """Turn the TV on."""
        await self._send_command(0x00, 0x00, 0x00, PowerCommand.ON.value)
        self._update_state(power=True)

    async def power_off(self) -> None:
        """Turn the TV off (standby)."""
        await self._send_command(0x00, 0x00, 0x00, PowerCommand.OFF.value)
        self._update_state(power=False)

    async def power_toggle(self) -> None:
        """Toggle TV power."""
        await self._send_command(0x00, 0x00, 0x00, PowerCommand.TOGGLE.value)

    async def set_volume(self, level: int) -> None:
        """Set the volume directly (0-100)."""
        if not 0 <= level <= MAX_VOLUME:
            raise ValueError(f"Volume must be 0-{MAX_VOLUME}, got {level}")
        await self._send_command(0x01, 0x00, 0x00, level)
        self._update_state(volume=level)

    async def volume_up(self) -> None:
        """Increase the volume by one step."""
        await self.send_key(Key.KEY_VOLUP)

    async def volume_down(self) -> None:
        """Decrease the volume by one step."""
        await self.send_key(Key.KEY_VOLDOWN)

    async def mute(self) -> None:
        """Toggle mute."""
        await self._send_command(0x02, 0x00, 0x00, 0x00)
        if self._state.mute is not None:
            self._update_state(mute=not self._state.mute)

    async def set_mute(self, muted: bool) -> None:
        """Set mute to an absolute state.

        The TV only exposes a mute toggle, so this reads the current mute
        state (querying the TV when it is unknown) and toggles only when it
        differs from the requested state.
        """
        current = self._state.mute
        if current is None:
            current = await self.query_mute()
        if current != muted:
            await self.mute()

    async def channel_up(self) -> None:
        """Channel up."""
        await self.send_key(Key.KEY_CHUP)

    async def channel_down(self) -> None:
        """Channel down."""
        await self.send_key(Key.KEY_CHDOWN)

    async def select_input_source(self, source: InputSource) -> None:
        """Switch to the given input source."""
        cmd3, value = source.value
        await self._send_command(0x0A, 0x00, cmd3, value)
        self._update_state(input_source=source)

    async def set_picture_mode(self, mode: PictureMode) -> None:
        """Set the picture mode."""
        await self._send_command(0x0B, 0x00, 0x00, mode.value)
        self._update_state(picture_mode=mode)

    async def set_sound_mode(self, mode: SoundMode) -> None:
        """Set the sound mode."""
        await self._send_command(0x0C, 0x00, 0x00, mode.value)
        self._update_state(sound_mode=mode)

    async def set_art_mode(self, on: bool) -> None:
        """Toggle Art Mode (Frame TVs)."""
        await self._send_command(0x0B, 0x0B, 0x0E, 0x01 if on else 0x00)

    async def set_ambient_mode(self, on: bool) -> None:
        """Toggle Ambient Mode."""
        await self._send_command(0x0B, 0x0B, 0x10, 0x01 if on else 0x00)

    async def set_hdmi_cec(self, on: bool) -> None:
        """Enable or disable HDMI CEC (Anynet+)."""
        await self._send_command(0x0B, 0x0B, 0x0F, 0x01 if on else 0x00)

    async def send_key(self, key: Key | int) -> None:
        """Send a remote-control keypress (cmd1=0x0d).

        Accepts a ``Key`` enum or a raw byte value.
        """
        value = key.value if isinstance(key, Key) else key
        await self._send_command(0x0D, 0x00, 0x00, value)

    async def send_raw(self, cmd1: int, cmd2: int, cmd3: int, value: int) -> bytes:
        """Send a raw command frame and return the 3-byte response.

        The response is returned without ack/nack interpretation -- callers
        that want ``CommandRejected`` semantics should use ``_send_command``.
        """
        async with self._write_lock:
            return await self._send_and_wait(cmd1, cmd2, cmd3, value)

    # -- Status queries --
    #
    # These use the cmd1=0xF0 query frame. The TV replies with the standard
    # 3-byte ACK followed by ``03 0c f5`` plus a 10-byte payload carrying the
    # requested value.

    async def _query(self, category: QueryCategory) -> QueryResponse:
        async with self._write_lock:
            response = await self._send_and_wait(
                0xF0, category.value, 0x00, 0x00, expect_query=True
            )
        if not isinstance(response, QueryResponse):
            raise SamsungTVError(
                f"Expected query response for {category.name}, got {response!r}"
            )
        return response

    async def query_power(self) -> PowerState:
        """Query the TV's power state."""
        resp = await self._query(QueryCategory.POWER)
        state = PowerState(resp.value)
        self._update_state(power=(state is PowerState.ON))
        return state

    async def query_volume(self) -> int:
        """Query the current volume (0-100)."""
        resp = await self._query(QueryCategory.VOLUME)
        self._update_state(volume=resp.value)
        return resp.value

    async def query_mute(self) -> bool:
        """Query the current mute state."""
        resp = await self._query(QueryCategory.MUTE)
        muted = resp.value != 0
        self._update_state(mute=muted)
        return muted

    async def query_channel(self) -> tuple[int, int, int]:
        """Query the current channel as ``(major, mid, minor)``."""
        resp = await self._query(QueryCategory.CHANNEL)
        return resp.channel_number

    async def query_source(self) -> int:
        """Query the current source byte.

        The mapping of byte -> input differs by TV generation. Use
        ``query_source_input()`` to translate to an ``InputSource`` if the
        TV's source map has been probed or supplied.
        """
        resp = await self._query(QueryCategory.SOURCE)
        return resp.value

    async def query_source_input(self) -> InputSource | None:
        """Query the current input source as an ``InputSource``.

        Requires ``source_map`` to have been populated either via
        ``probe_sources()`` or by passing it to the constructor. Returns
        ``None`` if the reported byte is not in the map.
        """
        byte = await self.query_source()
        for source, mapped in self._source_map.items():
            if mapped == byte:
                self._update_state(input_source=source)
                return source
        return None

    async def probe_sources(
        self, *, settle: float = 2.0, restore: bool = True
    ) -> dict[InputSource, int]:
        """Probe which input sources this TV supports.

        Iterates through every ``InputSource``, sends the corresponding
        select command, waits ``settle`` seconds for the TV to switch, then
        queries the current source byte. The first ``InputSource`` to
        produce a given byte wins -- subsequent sources that collapse onto
        the same byte (e.g. ``DVI1`` falling back to the previous HDMI on
        a Frame TV that has no DVI port) are dropped.

        The result is stored on ``self`` (see ``source_map``) and returned
        so it can be persisted and passed to a future constructor call to
        skip this probe.

        If ``restore`` is True (default) the original active source is
        restored at the end -- but only if it was found during the probe.
        """
        if not self._connected:
            raise SamsungTVError("Not connected")

        original_byte = await self.query_source()
        mapping: dict[InputSource, int] = {}
        seen: set[int] = set()

        for source in InputSource:
            try:
                await self.select_input_source(source)
            except CommandRejected:
                continue
            except TimeoutError:
                continue
            await asyncio.sleep(settle)
            try:
                byte = await self.query_source()
            except (TimeoutError, SamsungTVError):
                continue
            if byte in seen:
                continue
            seen.add(byte)
            mapping[source] = byte

        self._source_map = dict(mapping)

        if restore:
            for source, byte in mapping.items():
                if byte == original_byte:
                    try:
                        await self.select_input_source(source)
                    except (CommandRejected, TimeoutError):
                        pass
                    break

        return mapping

    async def refresh(self) -> None:
        """Refresh power and, when the TV is on, volume/mute/source.

        A powered-off Samsung TV does not answer status queries -- that is
        expected, not an error. When the power query times out (or reports a
        non-on state) ``power`` is set to ``False`` and the remaining
        attributes are left untouched. Connection errors propagate so the
        caller can tear down and reconnect.

        ``input_source`` is only refreshed when a source map is configured,
        since the raw source byte cannot otherwise be translated.
        """
        try:
            power = await self.query_power()
        except TimeoutError:
            self._update_state(power=False)
            return

        if power is not PowerState.ON:
            return

        for query in (self.query_volume, self.query_mute):
            try:
                await query()
            except TimeoutError:
                pass

        if self._source_map:
            try:
                await self.query_source_input()
            except TimeoutError:
                pass

    # -- Internals --

    async def _send_command(self, cmd1: int, cmd2: int, cmd3: int, value: int) -> None:
        """Send a frame and raise CommandRejected on NACK."""
        async with self._write_lock:
            response = await self._send_and_wait(cmd1, cmd2, cmd3, value)
        assert isinstance(response, bytes)
        if is_ack(response):
            return
        if is_nack(response):
            raise CommandRejected(
                f"TV rejected command "
                f"{cmd1:02x} {cmd2:02x} {cmd3:02x} {value:02x}: "
                f"got {response.hex(' ')}"
            )
        raise SamsungTVError(
            f"Unexpected response to command "
            f"{cmd1:02x} {cmd2:02x} {cmd3:02x} {value:02x}: "
            f"{response.hex(' ')}"
        )

    async def _send_and_wait(
        self,
        cmd1: int,
        cmd2: int,
        cmd3: int,
        value: int,
        *,
        expect_query: bool = False,
    ) -> bytes | QueryResponse:
        """Write a frame and wait for the response.

        If ``expect_query`` is True, returns a parsed ``QueryResponse`` from
        the 16-byte composite reply (ACK + ``03 0c f5`` + 10-byte payload).
        Otherwise returns the raw 3-byte response.

        Caller MUST hold ``self._write_lock``.
        """
        if self._writer is None:
            raise SamsungTVError("Not connected")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes | QueryResponse] = loop.create_future()
        self._pending = PendingResponse(future=future)
        self._pending_expects_query = expect_query

        frame = build_frame(cmd1, cmd2, cmd3, value)
        _LOGGER.debug("Sending: %s", frame.hex(" "))
        try:
            try:
                self._writer.write(frame)
                await self._writer.drain()
            except Exception:
                _LOGGER.exception("Error writing to serial port")
                await self._teardown()
                raise
            return await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
        finally:
            self._pending = None
            self._pending_expects_query = False

    async def _teardown(self) -> None:
        """Tear down the connection."""
        if not self._connected:
            return
        self._connected = False

        current = asyncio.current_task()

        if self._read_task is not None and self._read_task is not current:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        self._read_task = None

        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

        self._notify_subscribers()

    async def _read_loop(self) -> None:
        """Continuously read responses and unsolicited frames from the TV."""
        assert self._reader is not None
        buf = b""

        while self._connected:
            try:
                data = await self._reader.read(64)
            except Exception:
                if not self._connected:
                    return
                _LOGGER.exception("Error reading from serial port")
                await self._teardown()
                return

            if not data:
                _LOGGER.warning("Serial connection closed")
                await self._teardown()
                return

            buf += data
            buf = self._consume(buf)

    def _consume(self, buf: bytes) -> bytes:
        """Consume as many complete frames from ``buf`` as possible.

        Returns the remaining (unconsumed) bytes. The TV emits these frame
        shapes:

        - 3-byte response: ``03 0c f1`` (ACK) / ``03 0c ff`` (NACK).
        - 3+10 = 13-byte query data: ``03 0c f5`` + 10-byte payload.
        - 7-byte command echoes starting with ``08 22`` (rare; some TVs).
        """
        while buf:
            first = buf[0]
            if first == 0x03:
                if len(buf) < 3:
                    return buf
                if buf[1] != 0x0C:
                    _LOGGER.debug("Dropping unrecognized byte: 0x%02x", first)
                    buf = buf[1:]
                    continue
                marker = buf[2]
                if marker == QUERY_DATA_FOLLOWS[2]:
                    # ``03 0c f5`` -- 10 more payload bytes follow.
                    if len(buf) < 3 + QUERY_PAYLOAD_LENGTH:
                        return buf
                    payload = buf[3 : 3 + QUERY_PAYLOAD_LENGTH]
                    buf = buf[3 + QUERY_PAYLOAD_LENGTH :]
                    self._handle_query_payload(payload)
                    continue
                response, buf = buf[:3], buf[3:]
                self._handle_response(response)
                continue
            if first == HEADER[0]:
                if len(buf) < 2:
                    return buf
                if buf[1] != HEADER[1]:
                    _LOGGER.debug("Dropping unrecognized byte: 0x%02x", first)
                    buf = buf[1:]
                    continue
                if len(buf) < FRAME_LENGTH:
                    return buf
                frame, buf = buf[:FRAME_LENGTH], buf[FRAME_LENGTH:]
                self._handle_command_frame(frame)
                continue
            _LOGGER.debug("Dropping unrecognized byte: 0x%02x", first)
            buf = buf[1:]
        return buf

    def _handle_query_payload(self, payload: bytes) -> None:
        _LOGGER.debug("Received query payload: %s", payload.hex(" "))
        try:
            parsed = parse_query_payload(payload)
        except ValueError as err:
            _LOGGER.warning("Bad query payload %s (%s)", payload.hex(" "), err)
            return
        if (
            self._pending is not None
            and self._pending_expects_query
            and not self._pending.future.done()
        ):
            self._pending.future.set_result(parsed)

    def _handle_response(self, response: bytes) -> None:
        _LOGGER.debug("Received response: %s", response.hex(" "))
        if (
            self._pending is not None
            and not self._pending.future.done()
        ):
            # When a query is in flight, the leading ACK precedes the payload
            # we actually want -- ignore it and wait for ``03 0c f5 ...``.
            if self._pending_expects_query and is_ack(response):
                return
            self._pending.future.set_result(response)
            return
        _LOGGER.debug("Unsolicited response ignored: %s", response.hex(" "))

    def _handle_command_frame(self, frame: bytes) -> None:
        """Handle a 7-byte command echo coming from the TV."""
        try:
            cmd1, cmd2, cmd3, value = parse_frame(frame)
        except ValueError as err:
            _LOGGER.debug("Bad command frame from TV: %s (%s)", frame.hex(" "), err)
            return
        _LOGGER.debug(
            "Received command frame: %02x %02x %02x %02x", cmd1, cmd2, cmd3, value
        )

    def _update_state(self, **changes: object) -> None:
        """Update the state and notify subscribers if anything changed."""
        changed = False
        for attr, new_value in changes.items():
            if getattr(self._state, attr) != new_value:
                setattr(self._state, attr, new_value)
                changed = True
        if changed:
            self._notify_subscribers()

    def _notify_subscribers(self) -> None:
        state = self._state.copy() if self._connected else None
        # Iterate a copy: a subscriber may unsubscribe (directly or by
        # triggering teardown) while being notified, mutating the list.
        for callback in list(self._subscribers):
            try:
                callback(state)
            except Exception:
                _LOGGER.exception("Error in state change callback %s", callback)


__all__ = [
    "ACK_RESPONSE",
    "NACK_RESPONSE",
    "RESPONSE_LENGTH",
    "CommandRejected",
    "SamsungTV",
    "SamsungTVError",
    "StateCallback",
]
