"""Constants and enums shared across the samsung_exlink package."""

from __future__ import annotations

from enum import Enum

BAUD_RATE = 9600
COMMAND_TIMEOUT = 2.0  # seconds to wait for an ack/nack response

# All Samsung consumer-TV commands are 7-byte frames:
#     [HEADER0][HEADER1][cmd1][cmd2][cmd3][value][checksum]
HEADER = b"\x08\x22"
FRAME_LENGTH = 7

# Response from the TV.
# The TV sends a 3-byte response after every command frame.
# 03 0C F1 = success / acknowledge (TV processed the command).
# 03 0C FF = no-op / failure on some firmwares.
# 03 0C F5 = query data follows (precedes a 10-byte query payload).
ACK_RESPONSE = b"\x03\x0c\xf1"
NACK_RESPONSE = b"\x03\x0c\xff"
QUERY_DATA_FOLLOWS = b"\x03\x0c\xf5"
RESPONSE_LENGTH = 3

# Query response (10-byte payload that follows ``03 0c f5``):
#     [QUERY_RESPONSE_HEADER0][QUERY_RESPONSE_HEADER1][category][0x00][0x00]
#     [0xF1][value][extra1][extra2][checksum]
# The checksum spans the leading ``03 0c f5`` plus the first 9 bytes of the
# payload (i.e. all 12 bytes before the checksum byte).
QUERY_RESPONSE_HEADER = b"\x08\xf0"
QUERY_PAYLOAD_LENGTH = 10


class PowerCommand(Enum):
    """Power command values (cmd1=0x00, cmd2=0x00, cmd3=0x00)."""

    TOGGLE = 0x00
    OFF = 0x01
    ON = 0x02


class PowerState(Enum):
    """Power state values returned by ``query_power``."""

    STANDBY = 0x04
    ON = 0x05
    OFF = 0x08


class QueryCategory(Enum):
    """Query categories for the cmd1=0xF0 status query."""

    POWER = 0x00
    VOLUME = 0x01
    MUTE = 0x02
    CHANNEL = 0x03
    SOURCE = 0x04


class InputSource(Enum):
    """TV input sources.

    Encoded as ``(cmd3, value)`` for the input command (cmd1=0x0a, cmd2=0x00).
    Source types: TV, AV1-3, S-Video1-3, Component1-3, PC1-3, HDMI1-4,
    DVI1-3, RVU.
    """

    TV = (0x00, 0x00)
    AV1 = (0x01, 0x00)
    AV2 = (0x01, 0x01)
    AV3 = (0x01, 0x02)
    S_VIDEO1 = (0x02, 0x00)
    S_VIDEO2 = (0x02, 0x01)
    S_VIDEO3 = (0x02, 0x02)
    COMPONENT1 = (0x03, 0x00)
    COMPONENT2 = (0x03, 0x01)
    COMPONENT3 = (0x03, 0x02)
    PC1 = (0x04, 0x00)
    PC2 = (0x04, 0x01)
    PC3 = (0x04, 0x02)
    HDMI1 = (0x05, 0x00)
    HDMI2 = (0x05, 0x01)
    HDMI3 = (0x05, 0x02)
    HDMI4 = (0x05, 0x03)
    DVI1 = (0x06, 0x00)
    DVI2 = (0x06, 0x01)
    DVI3 = (0x06, 0x02)
    RVU = (0x07, 0x00)


class PictureMode(Enum):
    """Picture mode values (cmd1=0x0b, cmd2=0x00, cmd3=0x00)."""

    DYNAMIC = 0x00
    STANDARD = 0x01
    MOVIE = 0x02
    NATURAL = 0x03
    CAL_NIGHT = 0x04
    CAL_DAY = 0x05
    BD_WISE = 0x06
    RELAX = 0x07


class SoundMode(Enum):
    """Sound mode values (cmd1=0x0c, cmd2=0x00, cmd3=0x00)."""

    STANDARD = 0x01
    MUSIC = 0x02
    MOVIE = 0x03
    CLEAR_VOICE = 0x04
    AMPLIFY = 0x05
    OPTIMIZED = 0x06


class ColorTone(Enum):
    """Color tone values (cmd1=0x0b, cmd2=0x0a, cmd3=0x00)."""

    COOL = 0x00
    STANDARD = 0x01
    WARM1 = 0x02
    WARM2 = 0x03


class PictureSize(Enum):
    """Picture size / aspect ratio (cmd1=0x0b, cmd2=0x0a, cmd3=0x01)."""

    SIXTEEN_NINE = 0x00
    FOUR_THREE = 0x04
    CUSTOM = 0x0B


class Key(Enum):
    """KEY codes for the key-generation command (cmd1=0x0d, cmd2=0x00, cmd3=0x00).

    Sending a key emulates the corresponding remote button press.
    """

    KEY_SOURCE = 0x01
    KEY_POWER = 0x02
    KEY_SLEEP = 0x03
    KEY_1 = 0x04
    KEY_2 = 0x05
    KEY_3 = 0x06
    KEY_VOLUP = 0x07
    KEY_4 = 0x08
    KEY_5 = 0x09
    KEY_6 = 0x0A
    KEY_VOLDOWN = 0x0B
    KEY_7 = 0x0C
    KEY_8 = 0x0D
    KEY_9 = 0x0E
    KEY_MUTE = 0x0F
    KEY_CHDOWN = 0x10
    KEY_0 = 0x11
    KEY_CHUP = 0x12
    KEY_PRECH = 0x13
    KEY_GREEN = 0x14
    KEY_YELLOW = 0x15
    KEY_BLUE = 0x16
    KEY_MENU = 0x1A
    KEY_TV = 0x1B
    KEY_INFO = 0x1F
    KEY_MINUS = 0x23
    KEY_CAPTION = 0x25
    KEY_TTX_MIX = 0x2C
    KEY_EXIT = 0x2D
    KEY_OK = 0x2E
    KEY_FACTORY = 0x3B
    KEY_3SPEED = 0x3C
    KEY_EMANUAL = 0x3F
    KEY_STOP = 0x46
    KEY_PLAY = 0x47
    KEY_REC = 0x49
    KEY_PAUSE = 0x4A
    KEY_TOOLS = 0x4B
    KEY_GUIDE = 0x4F
    KEY_RETURN = 0x58
    KEY_SUBTITLE = 0x59
    KEY_UP = 0x60
    KEY_DOWN = 0x61
    KEY_RIGHT = 0x62
    KEY_LEFT = 0x65
    KEY_CH_LIST = 0x6B
    KEY_RED = 0x6C
    KEY_HOME = 0x76
    KEY_SMARTHUB = 0x79
    KEY_HDMI = 0x8B
    KEY_HARD_POWER = 0x98
    KEY_PAGE_LEFT = 0xA8
    KEY_PAGE_RIGHT = 0xA9
