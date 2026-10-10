"""Tests for the SamsungTV class."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import patch

import pytest

from conftest import MockSerialConnection
from samsung_exlink import (
    ACK_RESPONSE,
    NACK_RESPONSE,
    CommandRejected,
    InputSource,
    Key,
    PictureMode,
    PowerState,
    SamsungTV,
    SamsungTVConnectionError,
    SamsungTVError,
    SoundMode,
    UnknownPowerState,
    build_frame,
)


async def test_power_on_sends_correct_frame_and_updates_state(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.power_on()
    assert mock_serial.last_frame.hex(" ") == "08 22 00 00 00 02 d4"
    assert tv.power is True
    assert tv.state.power is True


async def test_power_off_sends_correct_frame_and_updates_state(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.power_off()
    assert mock_serial.last_frame.hex(" ") == "08 22 00 00 00 01 d5"
    assert tv.power is False


async def test_set_volume_25(tv: SamsungTV, mock_serial: MockSerialConnection) -> None:
    await tv.set_volume(25)
    assert mock_serial.last_payload == (0x01, 0x00, 0x00, 25)
    assert tv.state.volume == 25


async def test_set_volume_validates_range(tv: SamsungTV) -> None:
    with pytest.raises(ValueError):
        await tv.set_volume(101)
    with pytest.raises(ValueError):
        await tv.set_volume(-1)


async def test_mute_toggle(tv: SamsungTV, mock_serial: MockSerialConnection) -> None:
    await tv.mute()
    assert mock_serial.last_payload == (0x02, 0x00, 0x00, 0x00)


async def test_volume_up_uses_key_command(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.volume_up()
    assert mock_serial.last_payload == (0x0D, 0x00, 0x00, Key.KEY_VOLUP.value)


async def test_select_input_hdmi1(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.select_input_source(InputSource.HDMI1)
    assert mock_serial.last_payload == (0x0A, 0x00, 0x05, 0x00)
    assert tv.state.input_source is InputSource.HDMI1


async def test_select_input_hdmi3(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.select_input_source(InputSource.HDMI3)
    assert mock_serial.last_payload == (0x0A, 0x00, 0x05, 0x02)


async def test_set_picture_mode_movie(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.set_picture_mode(PictureMode.MOVIE)
    assert mock_serial.last_payload == (0x0B, 0x00, 0x00, PictureMode.MOVIE.value)
    assert tv.state.picture_mode is PictureMode.MOVIE


async def test_set_sound_mode_music(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.set_sound_mode(SoundMode.MUSIC)
    assert mock_serial.last_payload == (0x0C, 0x00, 0x00, SoundMode.MUSIC.value)
    assert tv.state.sound_mode is SoundMode.MUSIC


async def test_set_art_mode_on(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.set_art_mode(True)
    assert mock_serial.last_payload == (0x0B, 0x0B, 0x0E, 0x01)
    assert tv.state.art_mode is True


async def test_select_input_leaves_art_mode(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """Selecting a source takes a Frame TV out of Art Mode."""
    await tv.set_art_mode(True)
    await tv.select_input_source(InputSource.HDMI1)
    assert tv.state.art_mode is False


async def test_set_ambient_mode_off(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.set_ambient_mode(False)
    assert mock_serial.last_payload == (0x0B, 0x0B, 0x10, 0x00)


async def test_send_key_menu(tv: SamsungTV, mock_serial: MockSerialConnection) -> None:
    await tv.send_key(Key.KEY_MENU)
    assert mock_serial.last_payload == (0x0D, 0x00, 0x00, 0x1A)


async def test_send_key_accepts_raw_int(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    await tv.send_key(0x42)
    assert mock_serial.last_payload == (0x0D, 0x00, 0x00, 0x42)


async def test_nack_raises_command_rejected(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    mock_serial.set_auto_response(NACK_RESPONSE)
    with pytest.raises(CommandRejected):
        await tv.power_on()


async def test_send_raw_returns_response(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    response = await tv.send_raw(0x0D, 0x00, 0x00, 0x76)
    assert response == ACK_RESPONSE
    assert mock_serial.last_payload == (0x0D, 0x00, 0x00, 0x76)


async def test_subscribe_receives_state_changes(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    states: list = []
    unsubscribe = tv.subscribe(lambda s: states.append(s))
    try:
        await tv.power_on()
        await tv.set_volume(50)
    finally:
        unsubscribe()
    assert any(s and s.power is True for s in states)
    assert states[-1].volume == 50


async def test_unsubscribe_twice_is_noop(tv: SamsungTV) -> None:
    received: list = []
    unsubscribe = tv.subscribe(received.append)

    unsubscribe()
    unsubscribe()

    await tv.power_on()
    assert received == []


async def test_unsubscribe_frames_twice_is_noop(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    received: list[tuple[int, int, int, int]] = []
    unsubscribe = tv.subscribe_frames(lambda *frame: received.append(frame))

    unsubscribe()
    unsubscribe()

    mock_serial.feed(build_frame(0x0D, 0x00, 0x00, 0x07))
    await asyncio.sleep(0)
    assert received == []


async def test_disconnect_notifies_subscribers_with_none(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    states: list = []
    tv.subscribe(lambda s: states.append(s))
    await tv.disconnect()
    assert states[-1] is None


async def test_subscriber_unsubscribing_during_notify_does_not_skip_others(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A subscriber that unsubscribes mid-notify must not skip later ones."""
    seen_first: list = []
    seen_second: list = []

    def first(state):
        seen_first.append(state)
        unsubscribe_first()  # mutate the subscriber list during iteration

    unsubscribe_first = tv.subscribe(first)
    tv.subscribe(lambda s: seen_second.append(s))

    await tv.power_on()

    assert seen_first  # first ran
    assert seen_second  # second was not skipped despite the mutation


_BAD_CHECKSUM_FRAME = build_frame(0x0D, 0x00, 0x00, 0x07)[:6] + b"\x00"


@pytest.mark.parametrize(
    "noise",
    [
        pytest.param(b"\xaa\x55\x00", id="garbage"),
        pytest.param(b"\x03\x01", id="03-not-followed-by-0c"),
        pytest.param(b"\x08\x01", id="08-not-followed-by-22"),
        pytest.param(_BAD_CHECKSUM_FRAME, id="bad-checksum-frame"),
    ],
)
async def test_resync_after_noise(
    tv: SamsungTV, mock_serial: MockSerialConnection, noise: bytes
) -> None:
    """Bytes that do not form a valid frame are skipped up to the ACK."""
    mock_serial.set_auto_response(noise + ACK_RESPONSE)

    await tv.power_on()

    assert tv.state.power is True


async def test_split_query_payload_after_echo_frame(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """An echo frame ahead of a query reply split across reads is skipped."""
    reply = _query_response(0x01, 25)
    loop = asyncio.get_running_loop()

    def handler(_frame: bytes) -> None:
        mock_serial.feed(build_frame(0x0D, 0x00, 0x00, 0x07) + reply[:8])
        loop.call_later(0.005, mock_serial.feed, reply[8:])

    mock_serial.set_command_handler(handler)

    assert await tv.query_volume() == 25


async def test_subscribe_frames_receives_echo_frames(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    received: list[tuple[int, int, int, int]] = []
    unsubscribe = tv.subscribe_frames(lambda *frame: received.append(frame))

    mock_serial.feed(build_frame(0x0D, 0x00, 0x00, 0x07))
    await asyncio.sleep(0)
    assert received == [(0x0D, 0x00, 0x00, 0x07)]

    unsubscribe()
    mock_serial.feed(build_frame(0x0D, 0x00, 0x00, 0x0B))
    await asyncio.sleep(0)
    assert received == [(0x0D, 0x00, 0x00, 0x07)]


async def test_echo_frame_between_command_and_ack(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """An echo frame ahead of the ACK does not disturb the pending command."""
    received: list[tuple[int, int, int, int]] = []
    tv.subscribe_frames(lambda *frame: received.append(frame))
    mock_serial.set_auto_response(build_frame(0x0D, 0x00, 0x00, 0x07) + ACK_RESPONSE)

    await tv.power_on()

    assert received == [(0x0D, 0x00, 0x00, 0x07)]
    assert tv.state.power is True


async def test_split_response_bytes_are_buffered(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """Read loop must reassemble responses delivered byte-by-byte."""
    import asyncio

    loop = asyncio.get_running_loop()

    def handler(_frame: bytes) -> None:
        mock_serial.feed(b"\x03")
        loop.call_later(0.005, lambda: mock_serial.feed(b"\x0c\xf1"))

    mock_serial.set_command_handler(handler)
    await tv.power_on()


def _break_transport(mock_serial: MockSerialConnection) -> OSError:
    """Make the mock transport behave like a serial link that has gone away.

    Writes fail, and so does ``wait_closed()``: serialx re-raises the error
    that broke the connection when the stream is closed afterwards.
    """
    err = OSError(5, "ESPHome API connection closed")
    mock_serial.writer.write.side_effect = err
    mock_serial.writer.wait_closed.side_effect = err
    return err


async def test_write_error_on_broken_transport_tears_down(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A transport that also fails on close must not leave a dead writer behind."""
    received: list = []
    tv.subscribe(received.append)
    err = _break_transport(mock_serial)

    with pytest.raises(SamsungTVConnectionError) as exc_info:
        await tv.power_on()

    assert exc_info.value.__cause__ is err
    assert not tv.connected
    assert tv._writer is None
    assert tv._reader is None
    assert tv._read_task is None
    assert received == [None]

    # Later commands fail fast instead of writing to the dead stream again.
    mock_serial.writer.write.reset_mock()
    with pytest.raises(SamsungTVConnectionError, match="Not connected"):
        await tv.power_on()
    mock_serial.writer.write.assert_not_called()


async def test_link_loss_fails_command_in_flight(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A dropped link fails the pending query instead of timing out."""
    mock_serial.set_command_handler(lambda _frame: mock_serial.reader.feed_eof())

    with pytest.raises(SamsungTVConnectionError, match="Connection lost"):
        await tv.refresh()

    assert not tv.connected
    # A timeout would have been read as a powered-off TV.
    assert tv.state.power is None


async def test_read_error_on_broken_transport_tears_down(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """The read loop must finish cleanly even when closing the transport fails."""
    read_task = tv._read_task
    assert read_task is not None
    err = _break_transport(mock_serial)

    mock_serial.reader.set_exception(err)
    # Raised out of the task (and was left unretrieved) before the fix.
    await read_task

    assert not tv.connected
    assert tv._writer is None
    with pytest.raises(SamsungTVError, match="Not connected"):
        await tv.power_on()


async def test_read_loop_crash_tears_down(
    tv: SamsungTV,
    mock_serial: MockSerialConnection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected error in the read loop disconnects instead of hanging."""
    disconnected = asyncio.Event()
    tv.subscribe(lambda state: state is None and disconnected.set())

    with patch.object(tv, "_consume", side_effect=RuntimeError("boom")):
        mock_serial.feed(b"\x00")
        await disconnected.wait()

    assert not tv.connected
    assert "Read loop failed" in caplog.text


async def test_reconnect_after_broken_transport(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """After a broken link is torn down, connect() brings the TV back."""
    _break_transport(mock_serial)
    with pytest.raises(OSError):
        await tv.power_on()
    assert not tv.connected

    fresh = MockSerialConnection()

    async def fake_open(*args, **kwargs):
        return fresh.reader, fresh.writer

    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()

    assert tv.connected
    await tv.power_on()
    assert fresh.last_frame.hex(" ") == "08 22 00 00 00 02 d4"
    assert tv.power is True


async def test_connect_does_not_log_api_key(
    mock_serial: MockSerialConnection, caplog: pytest.LogCaptureFixture
) -> None:
    tv = SamsungTV("esphome://192.168.1.2/?port_name=TTL&key=SECRET")

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    caplog.set_level("INFO")
    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()
    await tv.disconnect()

    assert "esphome://192.168.1.2/" in caplog.text
    assert "SECRET" not in caplog.text


async def test_connect_when_connected_raises(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A second connect() must not replace and leak the open connection."""
    with (
        patch("samsung_exlink.tv.serialx.open_serial_connection") as mock_open,
        pytest.raises(SamsungTVError, match="Already connected"),
    ):
        await tv.connect()

    mock_open.assert_not_called()
    mock_serial.writer.close.assert_not_called()
    assert tv.connected
    await tv.power_on()


async def test_connect_failure_propagates(mock_serial: MockSerialConnection) -> None:
    tv = SamsungTV("/dev/ttyUSB0")
    err = OSError("no port")

    async def fake_open(*args, **kwargs):
        raise err

    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        with pytest.raises(OSError):
            await tv.connect()
    assert not tv.connected


async def test_power_toggle(tv: SamsungTV, mock_serial: MockSerialConnection) -> None:
    await tv.power_toggle()
    assert mock_serial.last_payload == (0x00, 0x00, 0x00, 0x00)


async def test_query_power_on(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """Query path: full ack + 03 0c f5 + 10-byte payload."""
    composite = bytes.fromhex(
        "03 0c f1 03 0c f5 08 f0 00 00 00 f1 05 00 00 0e"
    )
    mock_serial.set_auto_response(composite)
    state = await tv.query_power()
    assert state is PowerState.ON
    assert tv.state.power is True
    assert mock_serial.last_payload == (0xF0, 0x00, 0x00, 0x00)


async def test_query_power_full_off(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """Newer sets answer while fully off with 0x00."""
    mock_serial.set_command_handler(_status_handler(mock_serial, {0x00: 0x00}))
    tv._state.power = True

    state = await tv.query_power()

    assert state is PowerState.FULL_OFF
    assert tv.state.power is False


async def test_query_nack_raises_command_rejected(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    mock_serial.set_auto_response(NACK_RESPONSE)

    with pytest.raises(CommandRejected, match="POWER"):
        await tv.query_power()


async def test_refresh_when_queries_rejected(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A TV that rejects status queries leaves the state unknown."""
    mock_serial.set_auto_response(NACK_RESPONSE)

    await tv.refresh()

    assert tv.state.power is None
    assert len(mock_serial.written_frames) == 1


async def test_refresh_skips_rejected_queries_when_on(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """refresh() keeps going when the TV rejects one of the later queries."""

    def handler(frame: bytes) -> None:
        category = frame[3]
        if category == 0x00:
            mock_serial.feed(_query_response(0x00, 0x05))
        elif category == 0x02:
            mock_serial.feed(_query_response(0x02, 0x01))
        else:
            mock_serial.feed(NACK_RESPONSE)

    mock_serial.set_command_handler(handler)

    await tv.refresh()

    assert tv.state.power is True
    assert tv.state.volume is None
    assert tv.state.mute is True


async def test_query_power_unknown_byte(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    mock_serial.set_command_handler(_status_handler(mock_serial, {0x00: 0x07}))

    with pytest.raises(UnknownPowerState, match="0x07"):
        await tv.query_power()


async def test_refresh_unknown_power_byte_treated_as_off(
    tv: SamsungTV,
    mock_serial: MockSerialConnection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """refresh() reads an unknown power byte as off and warns only once."""
    mock_serial.set_command_handler(
        _status_handler(mock_serial, {0x00: 0x07, 0x01: 25, 0x02: 0x00})
    )

    await tv.refresh()
    await tv.refresh()

    assert tv.state.power is False
    assert tv.state.volume is None
    assert caplog.text.count("Unknown power state byte 0x07") == 1


async def test_query_volume(tv: SamsungTV, mock_serial: MockSerialConnection) -> None:
    composite = bytes.fromhex(
        "03 0c f1 03 0c f5 08 f0 01 00 00 f1 19 00 00 f9"
    )
    mock_serial.set_auto_response(composite)
    volume = await tv.query_volume()
    assert volume == 25
    assert tv.state.volume == 25


async def test_query_mute_off(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    composite = bytes.fromhex(
        "03 0c f1 03 0c f5 08 f0 02 00 00 f1 00 00 00 11"
    )
    mock_serial.set_auto_response(composite)
    muted = await tv.query_mute()
    assert muted is False
    assert tv.state.mute is False


async def test_query_source_returns_value_byte(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    # 0x4a = whatever this Frame TV reports for current input
    composite = bytes.fromhex(
        "03 0c f1 03 0c f5 08 f0 04 00 00 f1 4a 00 00 c5"
    )
    mock_serial.set_auto_response(composite)
    assert await tv.query_source() == 0x4A


async def test_query_payload_split_across_reads(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """Query payload arrives in multiple chunks; read loop must reassemble."""
    composite = bytes.fromhex(
        "03 0c f1 03 0c f5 08 f0 00 00 00 f1 05 00 00 0e"
    )
    loop = asyncio.get_running_loop()

    def handler(_frame: bytes) -> None:
        # Drip-feed in three chunks
        mock_serial.feed(composite[:4])
        loop.call_later(0.005, lambda: mock_serial.feed(composite[4:9]))
        loop.call_later(0.010, lambda: mock_serial.feed(composite[9:]))

    mock_serial.set_command_handler(handler)
    state = await tv.query_power()
    assert state is PowerState.ON


def _query_source_response(value: int) -> bytes:
    """Build a 16-byte SOURCE-query reply with the given value byte."""
    head = bytes.fromhex("03 0c f1 03 0c f5")
    payload9 = bytes([0x08, 0xF0, 0x04, 0x00, 0x00, 0xF1, value, 0x00, 0x00])
    chk = (256 - (sum(head[3:]) + sum(payload9)) & 0xFF) & 0xFF
    return head + payload9 + bytes([chk])


async def test_model_constructor_param_populates_source_map(
    mock_serial: MockSerialConnection,
) -> None:
    """Passing model= pre-populates source_map from the model's table."""
    from unittest.mock import patch as p

    from samsung_exlink.models import FRAME_2022

    tv = SamsungTV("/dev/ttyUSB0", model=FRAME_2022)

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with p(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()
    try:
        assert tv.model is FRAME_2022
        assert tv.source_map[InputSource.HDMI4] == 0x4A
        # Reverse lookup works without an explicit probe
        mock_serial.set_auto_response(_query_source_response(0x47))
        assert await tv.query_source_input() is InputSource.HDMI1
    finally:
        await tv.disconnect()


async def test_source_map_overrides_model(
    mock_serial: MockSerialConnection,
) -> None:
    """source_map=... wins over model.source_map for overlapping keys."""
    from unittest.mock import patch as p

    from samsung_exlink.models import FRAME_2022

    tv = SamsungTV(
        "/dev/ttyUSB0",
        model=FRAME_2022,
        source_map={InputSource.HDMI1: 0xAA},
    )

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with p(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()
    try:
        assert tv.source_map[InputSource.HDMI1] == 0xAA
        # Other model entries still present
        assert tv.source_map[InputSource.HDMI2] == 0x48
    finally:
        await tv.disconnect()


async def test_source_map_constructor_param(
    mock_serial: MockSerialConnection,
) -> None:
    from unittest.mock import patch

    preset = {InputSource.HDMI1: 0x47, InputSource.TV: 0x00}
    tv = SamsungTV("/dev/ttyUSB0", source_map=preset)

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()
    try:
        assert tv.source_map == preset
        # query_source_input should hit the map without probing
        mock_serial.set_auto_response(_query_source_response(0x47))
        assert await tv.query_source_input() is InputSource.HDMI1
        assert tv.state.input_source is InputSource.HDMI1
    finally:
        await tv.disconnect()


async def test_query_source_input_returns_none_when_byte_unknown(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    mock_serial.set_auto_response(_query_source_response(0xCC))
    assert await tv.query_source_input() is None


async def test_probe_sources_collapses_duplicates(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """probe_sources should drop sources that fall back onto an existing byte.

    Simulates a Frame-style TV: TV switches to 0x00, AV/Component/etc
    collapse back to 0x00, HDMI1-4 give 0x47..0x4a, and DVI/RVU collapse
    to 0x4a.
    """
    import samsung_exlink.tv as tv_module

    # Speed up the per-source settle wait for the test
    original_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await original_sleep(0)

    # Define what byte the TV will report after each select
    source_response_byte = {
        InputSource.TV: 0x00,
        InputSource.AV1: 0x00,
        InputSource.AV2: 0x00,
        InputSource.AV3: 0x00,
        InputSource.S_VIDEO1: 0x00,
        InputSource.S_VIDEO2: 0x00,
        InputSource.S_VIDEO3: 0x00,
        InputSource.COMPONENT1: 0x00,
        InputSource.COMPONENT2: 0x00,
        InputSource.COMPONENT3: 0x00,
        InputSource.PC1: 0x00,
        InputSource.PC2: 0x00,
        InputSource.PC3: 0x00,
        InputSource.HDMI1: 0x47,
        InputSource.HDMI2: 0x48,
        InputSource.HDMI3: 0x49,
        InputSource.HDMI4: 0x4A,
        InputSource.DVI1: 0x4A,
        InputSource.DVI2: 0x4A,
        InputSource.DVI3: 0x4A,
        InputSource.RVU: 0x4A,
    }

    current_source = InputSource.TV  # starting state

    def handler(frame: bytes) -> None:
        nonlocal current_source
        cmd1 = frame[2]
        if cmd1 == 0x0A:  # select_input_source
            mock_serial.feed(b"\x03\x0c\xf1")
            return
        if cmd1 == 0xF0:  # query
            cat = frame[3]
            if cat == 0x04:
                mock_serial.feed(_query_source_response(source_response_byte[current_source]))
            else:
                # ack for any other query — not used here
                mock_serial.feed(b"\x03\x0c\xf1")
            return
        mock_serial.feed(b"\x03\x0c\xf1")

    # The handler doesn't know the *previous* source, so override
    # select to advance the iterator.
    def select_handler(frame: bytes) -> None:
        nonlocal current_source
        cmd1 = frame[2]
        if cmd1 == 0x0A:
            # which source did we just send?
            cmd3, value = frame[4], frame[5]
            for s in InputSource:
                if s.value == (cmd3, value):
                    current_source = s
                    break
            mock_serial.feed(b"\x03\x0c\xf1")
        elif cmd1 == 0xF0 and frame[3] == 0x04:
            mock_serial.feed(_query_source_response(source_response_byte[current_source]))
        else:
            mock_serial.feed(b"\x03\x0c\xf1")

    mock_serial.set_command_handler(select_handler)

    with patch.object(tv_module.asyncio, "sleep", fast_sleep):
        mapping = await tv.probe_sources(settle=0)

    # First source per byte wins
    assert mapping == {
        InputSource.TV: 0x00,
        InputSource.HDMI1: 0x47,
        InputSource.HDMI2: 0x48,
        InputSource.HDMI3: 0x49,
        InputSource.HDMI4: 0x4A,
    }
    assert tv.source_map == mapping


async def test_late_response_not_credited_to_next_command(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A reply that misses the timeout must not answer the next command."""
    loop = asyncio.get_running_loop()

    def handler(frame: bytes) -> None:
        if frame[2] == 0x00:
            # power_on: the ACK only arrives after the command timed out.
            loop.call_later(0.15, mock_serial.feed, ACK_RESPONSE)
        else:
            # The TV answers in order, so this NACK follows the late ACK.
            loop.call_later(0.08, mock_serial.feed, NACK_RESPONSE)

    mock_serial.set_command_handler(handler)

    with pytest.raises(TimeoutError):
        await tv.power_on()
    with pytest.raises(CommandRejected):
        await tv.set_volume(10)
    assert tv.state.volume is None


async def test_timeout_when_no_response(mock_serial: MockSerialConnection) -> None:
    """If the TV never acks, the call raises TimeoutError."""
    tv = SamsungTV("/dev/ttyUSB0")
    mock_serial.set_auto_response(None)

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()
    try:
        with pytest.raises(TimeoutError):
            await tv.power_on()
    finally:
        await tv.disconnect()


def _query_response(category: int, value: int) -> bytes:
    """Build a 16-byte query reply for ``category`` carrying ``value``."""
    head = bytes.fromhex("03 0c f1 03 0c f5")
    payload9 = bytes([0x08, 0xF0, category, 0x00, 0x00, 0xF1, value, 0x00, 0x00])
    chk = (256 - (sum(head[3:]) + sum(payload9)) & 0xFF) & 0xFF
    return head + payload9 + bytes([chk])


def _status_handler(
    mock_serial: MockSerialConnection, values: dict[int, int]
) -> Callable[[bytes], None]:
    """Return a handler that answers each query category from ``values``."""

    def handler(frame: bytes) -> None:
        cmd1, category = frame[2], frame[3]
        if cmd1 == 0xF0 and category in values:
            mock_serial.feed(_query_response(category, values[category]))
        else:
            mock_serial.feed(ACK_RESPONSE)

    return handler


async def test_query_ignores_payload_for_other_category(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A payload for another category must not answer the pending query."""
    mock_serial.set_auto_response(_query_response(0x01, 0x05))

    with pytest.raises(TimeoutError):
        await tv.query_power()
    assert tv.state.power is None


async def test_mute_toggle_tracks_known_state(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A mute toggle flips a known mute state; it stays unknown otherwise."""
    await tv.mute()
    assert tv.state.mute is None

    tv._state.mute = False
    await tv.mute()
    assert tv.state.mute is True
    await tv.mute()
    assert tv.state.mute is False


async def test_set_mute_queries_then_toggles_when_unknown(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """set_mute reads the current state, then toggles since it differs."""
    mock_serial.set_command_handler(_status_handler(mock_serial, {0x02: 0x00}))

    await tv.set_mute(True)

    assert mock_serial.last_payload == (0x02, 0x00, 0x00, 0x00)
    assert tv.state.mute is True


async def test_concurrent_set_mute_toggles_once(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """Two concurrent set_mute(True) calls must not both toggle."""
    muted = False

    def handler(frame: bytes) -> None:
        nonlocal muted
        if frame[2] == 0xF0:
            mock_serial.feed(_query_response(0x02, int(muted)))
        else:
            muted = not muted
            mock_serial.feed(ACK_RESPONSE)

    mock_serial.set_command_handler(handler)

    await asyncio.gather(tv.set_mute(True), tv.set_mute(True))

    toggles = [f for f in mock_serial.written_frames if f[2] == 0x02]
    assert len(toggles) == 1
    assert muted is True


async def test_set_mute_noop_when_already_in_state(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """set_mute sends nothing when the TV is already in the requested state."""
    tv._state.mute = True
    await tv.set_mute(True)
    assert not mock_serial.written_frames


async def test_refresh_when_on_queries_volume_and_mute(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """refresh reads power, then volume and mute when the TV is on."""
    mock_serial.set_command_handler(
        _status_handler(mock_serial, {0x00: 0x05, 0x01: 25, 0x02: 0x00})
    )

    await tv.refresh()

    assert tv.state.power is True
    assert tv.state.volume == 25
    assert tv.state.mute is False


async def test_refresh_when_off_sets_power_false(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """A powered-off TV does not answer; refresh treats that as off."""
    mock_serial.set_auto_response(None)

    await tv.refresh()

    assert tv.state.power is False
    assert tv.state.volume is None


@pytest.mark.parametrize("power_byte", [0x00, 0x04, 0x08])
async def test_refresh_when_not_on_skips_remaining_queries(
    tv: SamsungTV, mock_serial: MockSerialConnection, power_byte: int
) -> None:
    """A TV that answers with a non-on power byte is off."""
    mock_serial.set_command_handler(
        _status_handler(mock_serial, {0x00: power_byte, 0x01: 25, 0x02: 0x00})
    )

    await tv.refresh()

    assert tv.state.power is False
    assert tv.state.volume is None
    assert tv.state.mute is None
    assert len(mock_serial.written_frames) == 1


@pytest.mark.parametrize(("value", "expected"), [(0x00, True), (0x01, False)])
async def test_query_art_mode(
    tv: SamsungTV, mock_serial: MockSerialConnection, value: int, expected: bool
) -> None:
    """Category 0x16 reads 0 in Art Mode and 1 otherwise."""
    mock_serial.set_command_handler(_status_handler(mock_serial, {0x16: value}))

    assert await tv.query_art_mode() is expected
    assert mock_serial.last_payload == (0xF0, 0x16, 0x00, 0x00)
    assert tv.state.art_mode is expected


async def test_refresh_queries_art_mode_for_frame(
    mock_serial: MockSerialConnection,
) -> None:
    """refresh reads Art Mode when the model reports it."""
    from samsung_exlink.models import FRAME_2022

    tv = SamsungTV("/dev/ttyUSB0", model=FRAME_2022)

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()
    try:
        mock_serial.set_command_handler(
            _status_handler(
                mock_serial, {0x00: 0x05, 0x01: 25, 0x02: 0x00, 0x04: 0x48, 0x16: 0x00}
            )
        )
        await tv.refresh()
        assert tv.state.art_mode is True
    finally:
        await tv.disconnect()


async def test_refresh_skips_art_mode_without_model(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    """refresh does not send the undocumented query to an unknown model."""
    mock_serial.set_command_handler(
        _status_handler(mock_serial, {0x00: 0x05, 0x01: 25, 0x02: 0x00, 0x16: 0x00})
    )

    await tv.refresh()

    assert tv.state.art_mode is None
    assert all(frame[3] != 0x16 for frame in mock_serial.written_frames)
