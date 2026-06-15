"""Known Samsung TV models / generations and their capabilities.

Different generations of Samsung consumer TVs map the same set of physical
inputs to different bytes in the ``cmd1=0xF0 cat=SOURCE`` query response.
A ``TVModel`` records the per-generation source map (and any other quirks
worth captring) so ``SamsungTV(port, model=...)`` can skip a probe.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import InputSource


@dataclass(frozen=True)
class TVModel:
    """Known capabilities of a Samsung TV model / generation."""

    name: str
    #: Map of ``InputSource`` to the byte that ``query_source()`` returns
    #: when that source is active.
    source_map: dict[InputSource, int]


# 2022 Frame (LS03B) and similar QLED / Neo QLED of the same generation.
# Probed against a real LS03B (May 2026).
FRAME_2022 = TVModel(
    name="Frame (2022)",
    source_map={
        InputSource.TV: 0x00,
        InputSource.HDMI1: 0x47,
        InputSource.HDMI2: 0x48,
        InputSource.HDMI3: 0x49,
        InputSource.HDMI4: 0x4A,
    },
)

# 2016 H-series (e.g. UN58H5203) -- values documented in
# https://github.com/NonaSuomy/SamsungTV-RS232-EX-LINK
H_SERIES_2016 = TVModel(
    name="H-series (2016)",
    source_map={
        InputSource.TV: 0x00,
        InputSource.AV1: 0x1C,
        InputSource.COMPONENT1: 0x29,
        InputSource.HDMI1: 0x39,
        InputSource.HDMI2: 0x3A,
    },
)


#: All known TV models, for iteration.
ALL_MODELS: tuple[TVModel, ...] = (
    FRAME_2022,
    H_SERIES_2016,
)

#: Models keyed by identifier string, for lookup.
MODELS: dict[str, TVModel] = {
    "frame_2022": FRAME_2022,
    "h_series_2016": H_SERIES_2016,
}
