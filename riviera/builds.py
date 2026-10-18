"""The game builds this toolkit knows, and the addresses that belong to each.

The text table is found by content (:mod:`riviera.nso`), but a few things inside the
executable are located by address: the string the engine builds its glyph table
from, and the width tables of the glyphs. They are fixed for one build, so a build
the toolkit has not seen is refused rather than patched blindly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SwitchBuild:
    title_id: str
    version: str
    build_id: str                 # first 20 bytes of the NSO module id, upper-case hex
    #: memory address of the string the engine turns into its character -> atlas cell table
    #: (the index of a character in the string is its cell)
    charset_addr: int
    #: ``(address of a pointer in .data to the table, first cell, last cell)``. Each table holds
    #: 6-byte entries ``(x0, width, y offset)`` for a run of cells.
    metric_tables: tuple[tuple[int, int, int], ...]
    #: the tables whose cells the accent patch writes into (the Latin-1 ranges)
    font_tables: tuple[tuple[int, int, int], ...]

    @property
    def ips_names(self) -> tuple[str, str]:
        """File names of the IPS patch: the full id (Eden, yuzu) and its first 16 bytes (Ryujinx, Atmosphere)."""
        return self.build_id, self.build_id[:32]


TITLE_ID = "01007D6025CB6000"

_METRICS = ((0xb65df0, 251, 332), (0xb65df8, 2204, 2261), (0xb65e00, 2378, 2386))

SWITCH_BUILDS = {
    "07432F4805A57F4527209EE4387072FB0F5D8A37": SwitchBuild(
        title_id=TITLE_ID, version="1.0.0", build_id="07432F4805A57F4527209EE4387072FB0F5D8A37",
        charset_addr=0x8bba14, metric_tables=_METRICS, font_tables=_METRICS[1:]),
}


class UnknownBuild(Exception):
    """The executable is not a build this toolkit has been taught."""


def for_build_id(build_id: str) -> SwitchBuild:
    """The :class:`SwitchBuild` for a module id as read from an NSO header (64 hex digits, zero padded)."""
    key = build_id.upper()[:40]
    try:
        return SWITCH_BUILDS[key]
    except KeyError:
        known = ", ".join(f"{b.version} ({b.build_id[:16]}…)" for b in SWITCH_BUILDS.values())
        raise UnknownBuild(f"build {key[:16]}… is not supported; known builds: {known}") from None


def for_nso(nso) -> SwitchBuild:
    return for_build_id(nso.build_id)
