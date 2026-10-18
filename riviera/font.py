"""Give the game's font the Spanish letters it is missing.

Dialogue is drawn from two glyph atlases, 3944 px wide (68x68 cells, 58 columns), inside
``data/System/systemTexture3.pck`` (``sysFont16.webp`` = soft-edged white glyphs,
``sysFont16_2.webp`` = white glyphs with a grey outline). At start-up the engine builds its
character -> cell table from a string in the executable (the index of a character in the
string is its cell). That string has 2494 characters = 43 rows and already includes
accented Latin-1 letters (cells 2204-2261 and 2378-2386) *with their metrics*, but this build
cut the atlas to 37 rows, so those cells have no picture.

This module grows the atlas back to 43 rows and draws, in their native cells, the glyphs that
Spanish needs (the base letter of each atlas plus an accent drawn here). ``¿`` and ``¡`` do not
exist in the game: they are written over the cells of ``Þ`` and ``Ð`` (the character in the
string and its metrics entry change). Nothing is taken from outside the game: every glyph is
made from the user's own atlas.
"""

from __future__ import annotations

import io
import json
import math
import os
import struct

from PIL import Image, ImageDraw, ImageFilter

from . import builds, metrics, pck
from .nso import HEADER

CELL, COLS, SS, ROWS = 68, 58, 4, 43
ORIG_ROWS = 37                           # rows the shipped atlas actually has
NATIVE = "áéíóúüñÁÉÍÓÚÜÑ"                 # already in the engine's character set
REPLACE = {"¿": "Þ", "¡": "Ð"}           # new character -> game character whose cell is reused
FLIP = {"¿": "？", "¡": "！"}             # obtained by turning the question / exclamation mark 180 degrees
BASE = {"á": "ａ", "é": "ｅ", "í": "ｉ", "ó": "ｏ", "ú": "ｕ", "ü": "ｕ", "ñ": "ｎ", "Á": "Ａ", "É": "Ｅ", "Í": "Ｉ",
        "Ó": "Ｏ", "Ú": "Ｕ", "Ñ": "Ｎ", "Ü": "Ｕ"}
ATLASES = ("sysFont16.webp", "sysFont16_2.webp")
ATLAS_PCK = "data/System/systemTexture3.pck"


def cell(im: Image.Image, i: int) -> Image.Image:
    r, c = divmod(i, COLS)
    return im.crop((c * CELL, r * CELL, c * CELL + CELL, r * CELL + CELL))


def put(im: Image.Image, i: int, cimg: Image.Image) -> None:
    r, c = divmod(i, COLS)
    im.paste(cimg, (c * CELL, r * CELL))


def _blank() -> Image.Image:
    return Image.new("L", (CELL * SS, CELL * SS), 0)


def _mask(big: Image.Image) -> Image.Image:
    return big.resize((CELL, CELL), Image.LANCZOS)


def m_acute(cx, top, h, w, t):
    big = _blank()
    ImageDraw.Draw(big).line([((cx - w / 2) * SS, (top + h) * SS), ((cx + w / 2) * SS, top * SS)], fill=255, width=int(t * SS))
    return _mask(big)


def m_dots(cx, cy, r, dx):
    big = _blank()
    d = ImageDraw.Draw(big)
    for x in (cx - dx, cx + dx):
        d.ellipse([(x - r) * SS, (cy - r) * SS, (x + r) * SS, (cy + r) * SS], fill=255)
    return _mask(big)


def m_tilde(cx, cy, w, amp, t):
    big = _blank()
    pts = [((cx - w / 2 + w * k / 40) * SS, (cy - amp * math.sin(2 * math.pi * k / 40)) * SS) for k in range(41)]
    ImageDraw.Draw(big).line(pts, fill=255, width=int(t * SS), joint="curve")
    return _mask(big)


def style1(mask: Image.Image) -> Image.Image:        # atlas 1: white with a soft edge
    a = mask.filter(ImageFilter.GaussianBlur(1.1)).point(lambda v: min(255, int(v * 1.25)))
    out = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    out.putalpha(a)
    return out


def style2(mask: Image.Image) -> Image.Image:        # atlas 2: white fill with a ~2 px grey outline
    o = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.5))
    out = Image.new("RGBA", mask.size, (66, 66, 66, 0))
    out.putalpha(o)
    fill = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    fill.putalpha(mask)
    out.alpha_composite(fill)
    return out


def shrink(c: Image.Image, k: float) -> Image.Image:
    """Scale the glyph by ``k``, resting on the same baseline and centred on the same axis."""
    bb = c.getchannel("A").getbbox()
    if not bb:
        return c
    g = c.crop(bb)
    w, h = g.size
    g = g.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    out = Image.new("RGBA", c.size, (0, 0, 0, 0))
    out.alpha_composite(g, (round((bb[0] + bb[2]) / 2 - g.size[0] / 2), bb[3] - g.size[1]))
    return out


def accent_mask(ch: str, cx: float, upper: bool) -> Image.Image:
    if ch in "áéíóúÁÉÍÓÚ":
        return m_acute(cx + 1, 3, 10 if upper else 11, 8 if upper else 10, 5 if upper else 6)
    if ch in "üÜ":
        return m_dots(cx, 6 if upper else 9, 3.6 if upper else 4.4, 7 if upper else 8.5)
    return m_tilde(cx, 6.5 if upper else 9.5, 22 if upper else 26, 2.6 if upper else 3.4, 4.6 if upper else 5.4)


def build_glyphs(idx_of: dict, a1: Image.Image, a2: Image.Image) -> dict:
    """``{character: (cell for atlas 1, cell for atlas 2)}`` with the new glyphs."""
    out = {}
    for ch, base in BASE.items():
        upper = ch.isupper()
        pair = []
        for im, style in ((a1, style1), (a2, style2)):
            c = cell(im, idx_of[base]).copy()
            bb = cell(a2, idx_of[base]).getchannel("A").getbbox()
            cx = (bb[0] + bb[2]) / 2
            if ch == "í":                                  # dotless i
                c.paste((0, 0, 0, 0), (0, 0, CELL, 22 if im is a1 else 21))
            if upper:
                c = shrink(c, 0.86)
            c.alpha_composite(style(accent_mask(ch, cx, upper)))
            pair.append(c)
        out[ch] = tuple(pair)
    for ch, src in FLIP.items():
        out[ch] = tuple(cell(im, idx_of[src]).rotate(180) for im in (a1, a2))
    return out


def charset(nso, build: builds.SwitchBuild | None = None) -> str:
    return metrics.charset_of(nso, build)


def cells_for(s: str) -> dict:
    """Cell of every new character: its own, or the one of the character it takes over."""
    cells = {ch: s.index(ch) for ch in NATIVE}
    cells.update({ch: s.index(old) for ch, old in REPLACE.items()})
    return cells


def ips_writes(nso, glyphs: dict, build: builds.SwitchBuild | None = None) -> dict:
    """Writes (offset in the NSO image -> bytes): the character string and the metrics of the new glyphs."""
    build = build or builds.for_nso(nso)
    s = charset(nso, build)
    cells = cells_for(s)
    offs, pos = [], 0
    for chx in s:
        offs.append(pos)
        pos += len(chx.encode("utf-8"))
    writes = {}
    for ch, old in REPLACE.items():                         # change the character of the cell (both are 2 bytes)
        i = cells[ch]
        if not len(old.encode()) == len(ch.encode()) == 2:
            raise ValueError("replacement characters must be 2 bytes long")
        writes[HEADER + build.charset_addr + offs[i]] = ch.encode("utf-8")
    for ch, (g1, g2) in glyphs.items():                     # metrics: x0 and width of the glyph (like the native ones)
        i = cells[ch]
        bb = g2.getchannel("A").getbbox()
        for slot, lo, hi in build.font_tables:
            if lo <= i <= hi:
                base = nso.relocs[slot]
                writes[HEADER + base + 6 * (i - lo)] = struct.pack("<HH", bb[0], bb[2] - bb[0])
    return writes


def font_metrics(nso, font_writes: dict, build: builds.SwitchBuild | None = None):
    """``(Metrics, charset)`` with the cells and widths the font patch adds."""
    build = build or builds.for_nso(nso)
    s = charset(nso, build)
    M = metrics.Metrics(nso, build=build)
    M.cell.update(cells_for(s))
    for slot, lo, hi in build.font_tables:
        base = HEADER + nso.relocs[slot]
        for off, data in font_writes.items():
            if base <= off < base + 6 * (hi - lo + 1):
                M.width[lo + (off - base) // 6] = struct.unpack("<HH", data)[1]
    return M, s


def missing_glyphs(chars, charset: str) -> dict:
    """Characters of the text that will not show: no cell in the font, or a cell with no picture in the atlas. The build cut
    the atlas to 37 rows (cells below 2146); the cells above only have a picture for the glyphs drawn here."""
    miss = {}
    drawn_limit = ORIG_ROWS * COLS
    injected = set(NATIVE) | set(REPLACE)
    for ch, n in chars.items():
        if ch in "\n;, []" or ch == "\0":              # brackets are in the English too ("[Nightmare]"): the engine draws them its own way
            continue
        o = ord(ch)
        probe = chr(o + 0xFEE0) if 0x21 <= o <= 0x7E else ch
        if ch in injected:
            continue
        i = charset.find(probe)
        if i < 0 or i >= drawn_limit:
            miss[ch] = n
    return miss


class Atlas:
    """The result of :func:`make_atlas`."""

    def __init__(self, pck_bytes, glyphs, cells, writes, atlases):
        self.pck = pck_bytes                # the new systemTexture3.pck
        self.glyphs = glyphs
        self.cells = cells
        self.writes = writes                # offset in the NSO image -> bytes
        self.atlases = atlases

    def sheet(self) -> Image.Image:
        """A contact sheet of the new glyphs on both atlases (for the eyes of a human)."""
        sheet = Image.new("RGB", (CELL * len(self.glyphs), CELL * 2), (70, 70, 90))
        for k, ch in enumerate(self.glyphs):
            for j, im in enumerate(self.atlases):
                c = cell(im, self.cells[ch])
                bg = Image.new("RGBA", c.size, (70, 70, 90, 255))
                bg.alpha_composite(c)
                sheet.paste(bg.convert("RGB"), (CELL * k, CELL * j))
        return sheet


def make_atlas(nso, pck_bytes: bytes, build: builds.SwitchBuild | None = None) -> Atlas:
    """Extend the atlases of ``systemTexture3.pck`` (given as bytes) and draw the Spanish glyphs."""
    build = build or builds.for_nso(nso)
    s = charset(nso, build)
    idx_of = {ch: i for i, ch in enumerate(s[:2134]) if ch != "　"}
    cells = cells_for(s)
    data0, ents = pck.read_pck(pck_bytes)
    names = pck.names(ents)
    pos = {n: names.index(n) for n in ATLASES}
    atlases = []
    for n in ATLASES:
        im = Image.open(io.BytesIO(ents[pos[n]][1])).convert("RGBA")
        big = Image.new("RGBA", (im.size[0], ROWS * CELL), (0, 0, 0, 0))
        big.paste(im, (0, 0))
        atlases.append(big)
    glyphs = build_glyphs(idx_of, *atlases)
    for ch, (g1, g2) in glyphs.items():
        put(atlases[0], cells[ch], g1)
        put(atlases[1], cells[ch], g2)
    for im, n in zip(atlases, ATLASES):
        buf = io.BytesIO()
        im.save(buf, "WEBP", lossless=True, quality=100, method=4)
        ents[pos[n]][1] = buf.getvalue()
    return Atlas(pck.write_pck(data0, ents), glyphs, cells, ips_writes(nso, glyphs, build), atlases)


def main(main_path, pck_path, out_dir):
    """Write ``out_dir/data/System/systemTexture3.pck``, ``muestra.png`` and ``ips.json`` (the layout the Android build reads)."""
    from .nso import Nso

    nso = Nso(main_path)
    atlas = make_atlas(nso, open(pck_path, "rb").read())
    dst = os.path.join(out_dir, "data", "System")
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "systemTexture3.pck"), "wb").write(atlas.pck)
    atlas.sheet().save(os.path.join(out_dir, "muestra.png"))
    json.dump({hex(o): d.hex() for o, d in atlas.writes.items()}, open(os.path.join(out_dir, "ips.json"), "w"), indent=1)
    print("glyphs:", "".join(atlas.glyphs), " IPS writes:", len(atlas.writes))
