"""Shared test fixtures for samsung_exlink."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import samsung_exlink.tv as samsung_tv
from samsung_exlink import ACK_RESPONSE, FRAME_LENGTH, NACK_RESPONSE, SamsungTV

# Speed up tests by reducing the command timeout.
samsung_tv.COMMAND_TIMEOUT = 0.1


class MockSerialConnection:
    """Mock the serial reader/writer pair with auto-ack support."""

    def __init__(self) -> None:
        self.reader = asyncio.StreamReader()
        self.writer = MagicMock()
        self.writer.write = MagicMock()
        self.writer.drain = AsyncMock()
        self.writer.close = MagicMock()
        self.writer.wait_closed = AsyncMock()
        self.written_frames: list[bytes] = []
        self._auto_response: bytes | None = ACK_RESPONSE
        self._command_handler: Callable[[bytes], None] | None = None
        self.writer.write.side_effect = self._on_write

    def _on_write(self, data: bytes) -> None:
        self.written_frames.append(data)
        if self._command_handler is not None:
            self._command_handler(data)
        elif self._auto_response is not None:
            self.feed(self._auto_response)

    def set_auto_response(self, response: bytes | None) -> None:
        """Set the response auto-fed after each write. None disables auto-feed."""
        self._auto_response = response

    def set_command_handler(self, handler: Callable[[bytes], None] | None) -> None:
        """Replace the auto-response with a custom per-command handler.

        While a handler is set, ``_auto_response`` is ignored.
        """
        self._command_handler = handler

    def feed(self, data: bytes) -> None:
        """Inject bytes into the read stream."""
        self.reader.feed_data(data)

    @property
    def last_frame(self) -> bytes:
        return self.written_frames[-1]

    @property
    def last_payload(self) -> tuple[int, int, int, int]:
        """Return ``(cmd1, cmd2, cmd3, value)`` from the last written frame."""
        frame = self.last_frame
        assert len(frame) == FRAME_LENGTH
        return frame[2], frame[3], frame[4], frame[5]


@pytest.fixture
async def mock_serial() -> MockSerialConnection:
    return MockSerialConnection()


@pytest.fixture
async def tv(mock_serial: MockSerialConnection):
    """Create a connected SamsungTV with a mocked serial connection."""
    tv = SamsungTV("/dev/ttyUSB0")

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with patch(
        "samsung_exlink.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()

    yield tv

    if tv.connected:
        await tv.disconnect()


__all__ = [
    "ACK_RESPONSE",
    "NACK_RESPONSE",
    "MockSerialConnection",
]
