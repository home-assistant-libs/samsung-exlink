# samsung-exlink

Async Python library to control Samsung consumer TVs over their RS232 serial
connection (Samsung markets this as "ExLink" / EX-Link / EXT Link).

## Project structure

```
src/samsung_exlink/
  __init__.py    -- Package re-exports.
  const.py       -- BAUD_RATE, HEADER, ACK/NACK/query consts, enums (InputSource,
                    Key, PictureMode, QueryCategory, PowerState, ColorTone, ...).
  protocol.py    -- build_frame, calculate_checksum, parse_frame, is_ack/is_nack,
                    parse_query_payload, QueryResponse, PendingResponse.
  state.py       -- TVState dataclass.
  models.py      -- TVModel + known per-generation source maps
                    (FRAME_2022, H_SERIES_2016).
  tv.py          -- SamsungTV class: connect/disconnect, commands, status
                    queries, source probing.
  __main__.py    -- CLI: power-on/off, volume(-up/down), mute, channel-up/down,
                    source, key, raw, status, listen.

tests/
  conftest.py          -- MockSerialConnection, fixtures (tv, mock_serial).
  test_protocol.py     -- Frame/checksum unit tests.
  test_samsung_tv.py   -- Command/state/query/error/timeout tests.
```

## Architecture

- Uses `serialx` (`open_serial_connection`) for async serial I/O (9600 8N1).
- Samsung consumer-TV protocol: fixed 7-byte frames `08 22 cmd1 cmd2 cmd3 value chk`,
  checksum = `(256 - sum(bytes 0..5)) & 0xFF`. TV replies `03 0C F1` (ACK) or
  `03 0C FF` (NACK).
- Most commands are fire-and-forget (ACK/NACK only). A subset of state --
  power, volume, mute, channel, source -- *can* be queried via the `cmd1=0xF0`
  status frame: the TV replies with the usual ACK, then `03 0C F5` followed by
  a 10-byte payload carrying the value (`parse_query_payload` -> `QueryResponse`).
  The library tracks a `TVState`, updated both when commands succeed and when
  a query returns.
- `connect()` opens the port and starts a `_read_loop`. There is no startup
  query.
- `_send_command` serializes through `_write_lock`: write a frame, wait for
  the next response, raise `CommandRejected` on NACK. Status queries share the
  same lock via `_send_and_wait(..., expect_query=True)`.
- `_read_loop` consumes a stream that may contain interleaved 3-byte response
  frames (`03 0C F1/FF`), 13-byte query-data frames (`03 0C F5` + 10-byte
  payload), and 7-byte echo frames (`08 22 ..`); split bytes are buffered.

## Key design decisions

- `Key` and `InputSource` are enums instead of strings (Samsung's protocol is
  binary).
- `InputSource` values are `(cmd2, cmd3)` tuples so `select_input_source()`
  is a one-liner.
- Power, volume, mute, source, picture_mode, sound_mode are first-class on
  `SamsungTV`; everything else uses `send_key(Key.X)` or `send_raw(...)`.
- There is one Samsung consumer-TV *command* protocol, so per-model
  capabilities (Frame Art Mode, Ambient Mode, etc.) just NACK on unsupported
  TVs. `models.py` exists only to record the one thing that *does* vary by
  generation: the byte `query_source()` returns for each input. Pass a
  `TVModel` (or a raw `source_map`) to the constructor to skip
  `probe_sources()`.

## Testing

- `pytest` with `pytest-asyncio`, `asyncio_mode = "auto"`, `timeout = 1`.
- `MockSerialConnection`: real `asyncio.StreamReader` + mock writer. Each
  write auto-feeds an ACK by default; tests can swap in a NACK or a custom
  per-frame handler.
- Run: `uv run pytest` or `python -m pytest tests/`.
- Lint: `uv run ruff check` (rules `E,F,I,UP,B`; config in `pyproject.toml`).
  CI runs both lint and pytest (3.12/3.13/3.14).

## Live testing setup

- ESPHome UART proxy at `192.168.1.29` exposes the TV's RS232 port.
  Connect with `serialx.open_serial_connection("esphome://192.168.1.29/?port_name=TTL", baudrate=9600)`.
- ESPHome IR proxy at `192.168.1.155` can transmit Samsung IR keys via
  `infrared-protocols`'s `SamsungTVCode` -- pressing a key on IR is observed
  on the RS232 link as a 7-byte command frame echo.

## Protocol reference

The full command map is in `docs/Samsung-RS232-Control.pdf`.
