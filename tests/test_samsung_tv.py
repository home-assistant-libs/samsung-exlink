"""Tests for the SamsungTV class."""

from __future__ import annotations

import asyncio
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
    SoundMode,
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


async def test_disconnect_notifies_subscribers_with_none(
    tv: SamsungTV, mock_serial: MockSerialConnection
) -> None:
    states: list = []
    tv.subscribe(lambda s: states.append(s))
    await tv.disconnect()
    assert states[-1] is None


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
