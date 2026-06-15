"""State for samsung_exlink.

The TV's state comes from two sources: the commands the library sends
(assuming the TV accepted them), and the ``query_*`` methods, which read
power/volume/mute/channel/source back from the TV. Fields default to ``None``
until first set or queried.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .const import InputSource, PictureMode, SoundMode


@dataclass
class TVState:
    """State of the Samsung TV.

    All fields default to ``None`` (unknown). They are populated as the user
    sends commands through the library and refreshed by the ``query_*``
    methods.
    """

    power: bool | None = None
    input_source: InputSource | None = None
    volume: int | None = None
    mute: bool | None = None
    picture_mode: PictureMode | None = None
    sound_mode: SoundMode | None = None

    def copy(self) -> TVState:
        return replace(self)
