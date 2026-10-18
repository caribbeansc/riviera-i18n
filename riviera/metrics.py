"""Glyph widths of the game's text engine, so lines can be broken at their real width.

The engine draws every character from a cell of the font atlas and advances by
``width of its metrics entry + 1`` units; a space (ASCII or full-width) advances a
fixed amount. The metrics entries (``x0, width, y offset``, 6 bytes each) live in
the executable's ``.rodata``, and the ASCII letters are drawn with the cells of the
full-width characters they stand for. A character with no metrics table (kanji and
the like) advances a whole cell.
"""

from __future__ import annotations

import struct

from . import builds

FULL = 68                      # advance of a whole cell, in atlas pixels
SPACE = 32                     # an ASCII space or U+3000 in proportional mode (value from the engine's code)


def charset_of(nso, build: builds.SwitchBuild | None = None) -> str:
    """The string the engine builds its glyph table from; the index of a character is its atlas cell."""
    build = build or builds.for_nso(nso)
    mem = nso.mem
    return mem[build.charset_addr:mem.index(b"\0", build.charset_addr)].decode("utf-8")


class Metrics:
    def __init__(self, nso, overrides=None, build: builds.SwitchBuild | None = None):
        build = build or builds.for_nso(nso)
        mem = nso.mem
        s = charset_of(nso, build)
        self.cell: dict[str, int] = {}
        for i, ch in enumerate(s):                      # the first cell with that character (as the engine's table)
            if ch != "　":
                self.cell.setdefault(ch, i)
        self.width: dict[int, int] = {}
        for slot, lo, hi in build.metric_tables:
            base = nso.relocs[slot]
            for i in range(lo, hi + 1):
                self.width[i] = struct.unpack_from("<HHH", mem, base + 6 * (i - lo))[1]
        if overrides:
            self.width.update(overrides)                # e.g. the metrics of the glyphs the patch writes

    def glyph(self, ch: str) -> int:
        o = ord(ch)
        if ch == " " or ch == "　":
            return SPACE
        if 0x21 <= o <= 0x7E:
            ch = chr(o + 0xFEE0)                        # ASCII -> full-width
        i = self.cell.get(ch)
        w = self.width.get(i)
        return FULL if w is None else w + 1

    def line(self, text: str) -> int:
        return sum(self.glyph(ch) for ch in text)
