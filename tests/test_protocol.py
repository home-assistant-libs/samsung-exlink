"""Tests for the framing/checksum helpers."""

from __future__ import annotations

import pytest

from samsung_exlink import (
    ACK_RESPONSE,
    NACK_RESPONSE,
    build_frame,
    calculate_checksum,
    is_ack,
    is_nack,
    parse_frame,
    parse_query_payload,
)


def test_power_off_frame_matches_pdf_example() -> None:
    """The Samsung PDF gives 08 22 00 00 00 01 D5 as power off."""
    frame = build_frame(0x00, 0x00, 0x00, 0x01)
    assert frame.hex(" ") == "08 22 00 00 00 01 d5"


def test_power_on_frame() -> None:
    frame = build_frame(0x00, 0x00, 0x00, 0x02)
    # 0x08+0x22+0x00+0x00+0x00+0x02 = 0x2C, 0x100 - 0x2C = 0xD4.
    assert frame.hex(" ") == "08 22 00 00 00 02 d4"


def test_volume_direct_25_frame() -> None:
    frame = build_frame(0x01, 0x00, 0x00, 25)
    assert frame == bytes.fromhex("08 22 01 00 00 19 bc")


def test_calculate_checksum_zero_payload() -> None:
    """Checksum of an all-zero payload is zero (256 mod 256)."""
    assert calculate_checksum(b"\x00\x00\x00\x00\x00\x00") == 0


def test_calculate_checksum_wraps_at_256() -> None:
    assert calculate_checksum(b"\x80\x80") == 0


def test_calculate_checksum_complements_to_zero() -> None:
    """The full frame including checksum sums to 0 mod 256."""
    payload = b"\x08\x22\x0d\x00\x00\x07"
    chk = calculate_checksum(payload)
    assert (sum(payload) + chk) % 256 == 0


def test_build_frame_validates_byte_range() -> None:
    with pytest.raises(ValueError):
        build_frame(256, 0, 0, 0)
    with pytest.raises(ValueError):
        build_frame(0, 0, 0, -1)


def test_parse_frame_round_trip() -> None:
    frame = build_frame(0x0A, 0x00, 0x05, 0x01)  # HDMI2
    assert parse_frame(frame) == (0x0A, 0x00, 0x05, 0x01)


def test_parse_frame_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        parse_frame(b"\x08\x22\x00\x00\x00\x01")  # 6 bytes
    with pytest.raises(ValueError):
        parse_frame(b"\x08\x22\x00\x00\x00\x01\xd5\x00")  # 8 bytes


def test_parse_frame_rejects_bad_header() -> None:
    with pytest.raises(ValueError):
        parse_frame(b"\xff\x22\x00\x00\x00\x01\xb8")


def test_parse_frame_rejects_bad_checksum() -> None:
    with pytest.raises(ValueError):
        parse_frame(b"\x08\x22\x00\x00\x00\x01\x00")


def test_is_ack_and_nack() -> None:
    assert is_ack(ACK_RESPONSE)
    assert not is_ack(NACK_RESPONSE)
    assert is_nack(NACK_RESPONSE)
    assert not is_nack(ACK_RESPONSE)


def test_parse_query_payload_power_on() -> None:
    """Real-world POWER query payload: TV is on (value 0x05)."""
    payload = bytes.fromhex("08 f0 00 00 00 f1 05 00 00 0e")
    parsed = parse_query_payload(payload)
    assert parsed.category == 0x00
    assert parsed.value == 0x05


def test_parse_query_payload_volume() -> None:
    payload = bytes.fromhex("08 f0 01 00 00 f1 05 00 00 0d")
    parsed = parse_query_payload(payload)
    assert parsed.category == 0x01
    assert parsed.value == 5


def test_parse_query_payload_channel_uses_three_bytes() -> None:
    payload = bytes.fromhex("08 f0 03 00 00 f1 86 ff 03 88")
    parsed = parse_query_payload(payload)
    assert parsed.channel_number == (0x86, 0xFF, 0x03)


def test_parse_query_payload_rejects_bad_checksum() -> None:
    payload = bytes.fromhex("08 f0 00 00 00 f1 05 00 00 00")
    with pytest.raises(ValueError):
        parse_query_payload(payload)


def test_parse_query_payload_rejects_bad_header() -> None:
    payload = bytes.fromhex("00 f0 00 00 00 f1 05 00 00 0e")
    with pytest.raises(ValueError):
        parse_query_payload(payload)
