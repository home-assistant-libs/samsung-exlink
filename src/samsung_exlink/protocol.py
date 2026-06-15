"""Protocol helpers for samsung_exlink.

The Samsung consumer-TV RS232 protocol uses fixed 7-byte frames::

    [0x08][0x22][cmd1][cmd2][cmd3][value][checksum]

The checksum is ``(256 - sum(bytes 0..5)) & 0xFF``, i.e. the two's-complement
negative of the sum so the entire frame mod-256-sums to zero.

The TV replies with a 3-byte frame: ``03 0C F1`` for success, ``03 0C FF`` for
NACK (invalid command / unsupported on the model).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .const import (
    ACK_RESPONSE,
    FRAME_LENGTH,
    HEADER,
    NACK_RESPONSE,
    QUERY_DATA_FOLLOWS,
    QUERY_PAYLOAD_LENGTH,
    QUERY_RESPONSE_HEADER,
)


def calculate_checksum(payload: bytes) -> int:
    """Return the Samsung RS232 checksum for the given payload bytes.

    ``payload`` is everything before the checksum byte: the two-byte header
    plus cmd1, cmd2, cmd3, and value (6 bytes total in normal use).
    """
    return (256 - (sum(payload) & 0xFF)) & 0xFF


def build_frame(cmd1: int, cmd2: int, cmd3: int, value: int) -> bytes:
    """Build a 7-byte command frame for the Samsung TV."""
    for name, byte in (
        ("cmd1", cmd1),
        ("cmd2", cmd2),
        ("cmd3", cmd3),
        ("value", value),
    ):
        if not 0 <= byte <= 0xFF:
            raise ValueError(f"{name} must be a byte (0-255), got {byte}")
    payload = HEADER + bytes((cmd1, cmd2, cmd3, value))
    return payload + bytes((calculate_checksum(payload),))


def parse_frame(frame: bytes) -> tuple[int, int, int, int]:
    """Parse a 7-byte command frame, returning ``(cmd1, cmd2, cmd3, value)``.

    Raises ``ValueError`` if the header is wrong, length is wrong, or the
    checksum does not match.
    """
    if len(frame) != FRAME_LENGTH:
        raise ValueError(f"Frame must be {FRAME_LENGTH} bytes, got {len(frame)}")
    if frame[:2] != HEADER:
        raise ValueError(f"Bad header: {frame[:2].hex()}")
    expected = calculate_checksum(frame[:6])
    if frame[6] != expected:
        raise ValueError(
            f"Bad checksum: got 0x{frame[6]:02x}, expected 0x{expected:02x}"
        )
    return frame[2], frame[3], frame[4], frame[5]


def is_ack(response: bytes) -> bool:
    """Return True if the response is a success ack."""
    return response == ACK_RESPONSE


def is_nack(response: bytes) -> bool:
    """Return True if the response is an explicit NACK."""
    return response == NACK_RESPONSE


@dataclass
class QueryResponse:
    """A parsed status-query payload from the TV.

    A full query response on the wire is 16 bytes::

        03 0c f1 03 0c f5 08 f0 [cat] 00 00 f1 [val] [ex1] [ex2] [chk]

    ``03 0c f1`` is the initial ACK; ``03 0c f5`` flags that a 10-byte data
    payload follows (the rest of the frame). The checksum is computed across
    the trailing 12 bytes -- ``03 0c f5`` plus the first nine payload bytes.
    """

    category: int
    value: int
    extra1: int
    extra2: int

    @property
    def channel_number(self) -> tuple[int, int, int]:
        """For category=CHANNEL: ``(major, mid, minor)`` from value/extra bytes."""
        return self.value, self.extra1, self.extra2


def parse_query_payload(payload: bytes) -> QueryResponse:
    """Parse a 10-byte query payload (the part after ``03 0c f5``).

    Raises ``ValueError`` on bad header or checksum.
    """
    if len(payload) != QUERY_PAYLOAD_LENGTH:
        raise ValueError(
            f"Query payload must be {QUERY_PAYLOAD_LENGTH} bytes, got {len(payload)}"
        )
    if payload[:2] != QUERY_RESPONSE_HEADER:
        raise ValueError(f"Bad query header: {payload[:2].hex()}")
    if payload[5] != 0xF1:
        raise ValueError(f"Missing F1 marker at byte 5: 0x{payload[5]:02x}")
    summed = sum(QUERY_DATA_FOLLOWS) + sum(payload[:9])
    expected = (256 - (summed & 0xFF)) & 0xFF
    if payload[9] != expected:
        raise ValueError(
            f"Bad query checksum: got 0x{payload[9]:02x}, expected 0x{expected:02x}"
        )
    return QueryResponse(
        category=payload[2], value=payload[6], extra1=payload[7], extra2=payload[8]
    )


@dataclass
class PendingResponse:
    """A pending response waiting on the read loop."""

    future: asyncio.Future[bytes]
