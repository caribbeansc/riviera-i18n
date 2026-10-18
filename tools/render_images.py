#!/usr/bin/env python3
"""Draw the translated pictures of a language (a contributor tool: the build never runs it).

Part of the game's text is baked into pictures: the intro, the scene titles, the captions of the illustrations, the chapter
cards, the epithets, the poem, the explanation of every option of the configuration screen. This tool redraws those pictures in
your language and writes the ``.pck`` packages that hold them. ``tools/images_pack.py`` then stores the result in the language
pack (``langs/<code>/images/``), so a player never needs this tool or its fonts. ``tools/README.md`` describes the whole workflow.

It draws with the **macOS system fonts** (Times New Roman, Apple Chancery, Futura, Tahoma...), so it only runs on a Mac that has
them; when a font file is missing it stops and names the font. Every style imitates the original picture: a similar typeface,
with the size, compression, baseline and margins measured on the original, so that the new text looks like the old one.

Usage::

    python tools/render_images.py --originals work/switch/data_en \\
        --spec langs/es/images/specs/narrative.json --spec langs/es/images/specs/explanations.json \\
        --out work/switch/rendered

``--originals``  the packages of your own ``data_en.bin`` as ``python rpl.py unpack`` writes them (``data/event/*.pck``,
                 ``data/System/*.pck``...). Default: ``work/switch/data_en``.
``--spec``       a render spec (see below). Repeat the option to merge several; the last one wins per entry.
``--out``        where to write the new packages, with the same layout (``<out>/data/event/demo1.pck``...). Only the packages
                 that the specs name are written. Default: ``work/switch/rendered``.
``--labels``     the calibration labels (see below). Default: ``work/switch/ocr/en_labels.json``.

(The defaults are under ``RPL_HOME`` when that is set, otherwise under the checkout.)

Specs
-----
A spec says what to draw in which picture of which package::

    {"event/demo1.pck": {"story_00.webp": {"estilo": "story", "texto": "..."}}}

The keys ``estilo`` (style) and ``texto`` (text) stay in Spanish on purpose: they are the names the shipped spec files use. Every
other key of an entry overrides one parameter of its style (``fill``, ``font``, ``maxw``, ``thr``, ``tbox``...; lists are read
as tuples). ``texto`` is a string, except for ``chapter`` (``["top line", "title"]``), ``chrcopy`` (``[["text", "small"],
["text", "big"]]``) and ``poem`` (nine strings), and ``lines`` takes its lines joined by ``|``. A picture that is a loose file
rather than an entry of a package is listed by its path, with the style and the text directly under it:
``{"skillname/eskillName01.webp": {"estilo": "skillname", "texto": "..."}}``.

Labels
------
The styles that measure the original picture (``auto``, ``patch``, ``lines``, ``flat_*``, ``skillname``) need its English text, to
know how big and how compressed the original letters are, and ``poem`` needs the nine English lines it cuts its letters from
(one label, the lines joined by ``|``). They are read from a JSON file ``{package: {entry: english text}}`` (the key ``""`` holds
loose files, by path) that ``tools/ocr.swift`` helps to make. **That file is the game's own text**: keep it under ``work/`` (ignored
by git) and never commit it. An entry can also carry the text itself in an ``en`` key. Styles that only draw text (``story``,
``title``, ``caption``...) need no label.

Styles
------
Pictures that tell the story (``narrative.json`` of the Spanish pack):

    story       intro lines: bold serif, light grey, a fixed canvas 64 px tall
    title       scene titles: Apple Chancery with a pale glow, fixed canvas, left aligned
    caption     captions of the illustrations: script face with a soft shadow, cropped to the ink
    chapter     chapter cards: black on transparent, two lines, right aligned
    mapname     subtitles of the world map: Futura capitals, right aligned
    chrcopy     the epithets of the intro: white serif with a thick black outline, parts of two sizes
    year        keeps the top line of the original and rewrites the bottom one, centred
    poem        the poem of the cut-in: the picture's own pixel typeface, cut from the original

Generic styles, calibrated on the original; every parameter can be given in the entry (the Spanish pack uses ``flat_tahoma`` and
``patch`` for the explanations of the options, ``explanations.json``):

    auto        rewrite a label so that its ink box matches the original's
    patch       keep a panel, button or icon: erase ``clear`` and write the text in the ink box ``tbox``
    lines       a label of several lines, separated by ``|``
    flat_tahoma, flat_gill, flat_trebu, flat_krung    ``auto`` with one typeface each
    skillname   skill names: white condensed face, black outline, soft shadow

Interface pictures (the Spanish pack keeps its interface in English and does not use these; another language may):

    titlebtn, titlebtn_sel    title-screen buttons, normal and selected: serif with a blue glow
    telop, telop_ex           screen headers: Art Deco initials with small capitals / a squared face
    nodata                    the empty-slot panel of the save screen
    evshot, escape, atprompt, atcaption, largename, newskill, unknown, noskill, stageclear    banners
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from riviera.config import user_dir  # noqa: E402
from riviera.images import encode_webp  # noqa: E402  (lossless WebP, quality 100, method 4: how the packages hold the artwork)
from riviera.pck import entry_name, read_pck, write_pck  # noqa: E402


class RenderError(Exception):
    """Something the contributor can fix: a missing font, label or picture, an unknown style, text that cannot fit."""


# --------------------------------------------------------------------------- fonts ---

_SYS = "/System/Library/Fonts/"
_SUP = _SYS + "Supplemental/"

#: Name used by the styles and the specs -> (file, index inside a ``.ttc`` collection).
FONTS = {
    "times_bold": (_SUP + "Times New Roman Bold.ttf", 0),
    "times": (_SUP + "Times New Roman.ttf", 0),
    "tnr_italic": (_SUP + "Times New Roman Italic.ttf", 0),
    "tnr_bolditalic": (_SUP + "Times New Roman Bold Italic.ttf", 0),
    "arial_rounded": (_SUP + "Arial Rounded Bold.ttf", 0),
    "impact": (_SUP + "Impact.ttf", 0),
    "didot_reg": (_SUP + "Didot.ttc", 0),
    "georgia_bi": (_SUP + "Georgia Bold Italic.ttf", 0),
    "optima": (_SYS + "Optima.ttc", 0),
    "snell_bold": (_SUP + "SnellRoundhand.ttc", 1),
    "hoefler": (_SUP + "Hoefler Text.ttc", 0),
    "baskerville": (_SUP + "Baskerville.ttc", 0),
    "dincond": (_SUP + "DIN Condensed Bold.ttf", 0),
    "didot_bold": (_SUP + "Didot.ttc", 2),
    "palatino": (_SYS + "Palatino.ttc", 0),
    "futura_bold": (_SUP + "Futura.ttc", 2),
    "chancery": (_SUP + "Apple Chancery.ttf", 0),
    "georgia_bold": (_SUP + "Georgia Bold.ttf", 0),
    "futura_cexb": (_SUP + "Futura.ttc", 4),
    "avenir_cond": (_SYS + "Avenir Next Condensed.ttc", 7),
    "krungthep": (_SUP + "Krungthep.ttf", 0),
    "tahoma": (_SUP + "Tahoma.ttf", 0),
    "trebuchet": (_SUP + "Trebuchet MS.ttf", 0),
    "gill": (_SUP + "GillSans.ttc", 0),
    "avenir_reg": (_SYS + "Avenir Next.ttc", 7),
    "verdana": (_SUP + "Verdana.ttf", 0),
    "optima_reg": (_SYS + "Optima.ttc", 0),
    "din_cond": (_SUP + "DIN Condensed Bold.ttf", 0),
    "arial_black": (_SUP + "Arial Black.ttf", 0),
    "arial_narrow_b": (_SUP + "Arial Narrow Bold.ttf", 0),
}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """The font called ``name`` at ``size`` px. Stops with a message that names the font when this Mac does not have its file."""
    try:
        path, index = FONTS[name]
    except KeyError:
        raise RenderError(f"unknown font {name!r}; the known ones are: {', '.join(sorted(FONTS))}") from None
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError as exc:
        if not Path(path).is_file():
            raise RenderError(
                f"the font {name!r} needs {path}, which is not on this machine. This tool draws with macOS system fonts, "
                "so it only runs on a Mac that has them; it is a contributor tool and not part of the build.") from exc
        raise RenderError(f"the font {name!r} could not be opened from {path} (face {index}): {exc}") from exc


# ------------------------------------------------------------------ drawing helpers ---

def ink_mask(text, fname, size, baseline, height, hscale=1.0, tracking=0.0, autofit=3):
    """``L`` mask of the text on the given baseline: a fixed ``height`` and a width fitted to the ink (tracking in px).

    If any mark (the accent of a capital, say) would leave the canvas through the top, the body shrinks until it fits."""
    f = font(fname, size)
    wn = f.getlength(text) + tracking * len(text)
    m = Image.new("L", (int(wn) + 60, height + 80), 0)
    d = ImageDraw.Draw(m)
    if tracking:
        x = 30.0
        for ch in text:
            d.text((x, baseline + 40), ch, font=f, fill=255, anchor="ls")
            x += f.getlength(ch) + tracking
    else:
        d.text((30, baseline + 40), text, font=f, fill=255, anchor="ls")
    bb = m.getbbox()
    if bb and autofit and bb[1] < 40 and size > 12:
        new_size = int(size * baseline / (baseline + 40 - bb[1]) * 0.99)
        return ink_mask(text, fname, max(10, min(new_size, size - 1)), baseline, height, hscale, tracking, autofit - 1)
    if not bb:
        return Image.new("L", (1, height), 0)
    m = m.crop((bb[0], 40, bb[2], 40 + height))
    return m.resize((max(1, round(m.size[0] * hscale)), height), Image.LANCZOS)


def colorize(mask, rgb):
    out = Image.new("RGBA", mask.size, rgb + (0,))
    out.putalpha(mask)
    return out


def with_shadow(layer, shadow, pad):
    """A blurred black shadow under an RGBA layer (``shadow`` = (radius, opacity, dx, dy))."""
    r, op, dx, dy = shadow
    a = layer.getchannel("A").filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v * op))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a)
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (dx, dy))
    out.alpha_composite(layer)
    return out


def fit_size(text, st, size, hscale=1.0, minscale=1.0):
    """The largest body (``<= size``) at which the text, compressed down to ``minscale``, fits in ``maxw``."""
    for s in range(size, 19, -1):
        width = font(st["font"], s).getlength(text) + st.get("tracking", 0.0) * len(text) * s / st.get("size", s)
        if width * minscale <= st["maxw"]:
            return s
    return 20


def with_glow(mask, glow, outline):
    """A pale blurred halo, a thin dark outline and the fill (``mask`` is the ``L`` fill)."""
    r, op, rgb = glow
    g = mask.filter(ImageFilter.GaussianBlur(r)).point(lambda v: min(255, int(v * op * 1.6)))
    out = colorize(g, rgb)
    if outline:
        o = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(outline * 0.4))
        out.alpha_composite(colorize(o, (10, 12, 14)))
    return out


def cap_ratio(fname, ref):
    """Height of the reference glyph per px of the font's body."""
    f = font(fname, 200)
    m = Image.new("L", (700, 520), 0)
    ImageDraw.Draw(m).text((60, 360), ref, font=f, fill=255, anchor="ls")
    bb = m.getbbox()
    return (bb[3] - bb[1]) / 200.0


def cap_size(fname, cap):
    """The body (px) at which the font's ``H`` is ``cap`` px tall."""
    f = font(fname, 200)
    bb = f.getbbox("H", anchor="ls")
    return 200.0 * cap / (bb[3] - bb[1])


def text_layer(text, fname, size, fill, stroke=0, stroke_fill=(0, 0, 0), shear=0.0, tracking=0.0):
    """An RGBA layer cropped to the ink (outline included) and the distance from its top edge to the baseline."""
    f = font(fname, size)
    stroke = int(round(stroke))
    pad = int(size * 0.5) + stroke + 10
    wn = int(f.getlength(text) + tracking * len(text)) + 2 * pad + int(abs(shear) * size * 1.2)
    base = pad + int(size * 1.0)
    m = Image.new("RGBA", (wn, base + int(size * 0.7) + pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(m)
    if tracking:
        if stroke:
            x = float(pad)
            for ch in text:
                d.text((x, base), ch, font=f, fill=stroke_fill, anchor="ls", stroke_width=stroke, stroke_fill=stroke_fill)
                x += f.getlength(ch) + tracking
        x = float(pad)
        for ch in text:
            d.text((x, base), ch, font=f, fill=fill, anchor="ls")
            x += f.getlength(ch) + tracking
    else:
        d.text((pad, base), text, font=f, fill=fill, anchor="ls", stroke_width=stroke, stroke_fill=stroke_fill)
    if shear:
        m = m.transform(m.size, Image.AFFINE, (1, shear, -shear * base, 0, 1, 0), Image.BICUBIC)
    bb = m.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bb:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), 0
    return m.crop(bb), base - bb[1]


def paste_clip(canvas, layer, x, y):
    """``alpha_composite`` that accepts offsets that are negative or partly outside the canvas."""
    W, H = canvas.size
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + layer.size[0]), min(H, y + layer.size[1])
    if x1 > x0 and y1 > y0:
        canvas.alpha_composite(layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


# ------------------------------------------------------------------- styles with a fixed look ---

#: Parameters measured on the original pictures (canvas width, baselines, capital heights, edges).
STYLES = {
    # height: the original canvas is 48 px tall, but with Times Bold the tails of g, p, y and q (about 13 px below the
    # baseline) were clipped, so the canvas is 64 px.
    "story":   dict(font="times_bold", size=54, fill=(224, 224, 224), hscale=0.952, baseline=38, height=64, maxw=1160, minscale=0.80),
    "title":   dict(font="chancery", size=86, fill=(214, 218, 220), glow=(6, 0.9, (216, 223, 225)), outline=1.6, tracking=9.0,
                    height=128, width=1280, baseline=88, left=38, maxw=1230),
    "caption": dict(font="snell_bold", size=102, fill=(224, 224, 224), shadow=(3, 0.6, 2, 3), margin=24, maxw=1840),
    "chapter": dict(width=1024, height=288, fill=(0, 0, 0), right=(989, 994), maxw=950,
                    top=dict(font="palatino", size=100, baseline=92, hscale=0.86, minscale=0.70),
                    main=dict(font="times_bold", size=150, baseline=240, hscale=0.72, minscale=0.55)),
    "mapname": dict(font="futura_bold", size=31, fill=(240, 240, 240), width=832, height=32, baseline=30, right=820, maxw=806, tracking=1.5),
    "chrcopy": dict(font="times_bold", width=512, height=160, baseline=118, small=80, big=104, hscale=0.62, fill=(240, 240, 240),
                    outline=(0, 0, 0), olw=7, maxw=494, left=9),
}


def render_story(text, st):
    """One line of the intro: a fixed canvas, compressed horizontally until it fits."""
    size = fit_size(text, st, st["size"], st["hscale"], st["minscale"])
    w_nat = font(st["font"], size).getlength(text)
    hs = min(st["hscale"], st["maxw"] / w_nat)
    return colorize(ink_mask(text, st["font"], size, st["baseline"], st["height"], hs), st["fill"])


def render_script(text, st):
    """A scene title (fixed canvas, left aligned, with a glow) or a caption (cropped to the ink, with a shadow)."""
    size = fit_size(text, st, st["size"])
    track = st.get("tracking", 0.0)
    if "width" in st:
        wn = font(st["font"], size).getlength(text) + track * len(text)
        if wn > st["maxw"]:
            size = max(20, int(size * st["maxw"] / wn))
            track *= size / st["size"]
        m = ink_mask(text, st["font"], size, st["baseline"], st["height"], 1.0, track)
        cv = Image.new("RGBA", (st["width"], st["height"]), (0, 0, 0, 0))
        mm = Image.new("L", (st["width"], st["height"]), 0)
        mm.paste(m, (st["left"], 0))
        cv.alpha_composite(with_glow(mm, st["glow"], st["outline"]))
        cv.alpha_composite(colorize(mm, st["fill"]))
        return cv
    # Cropped to the ink: the height depends on the strokes, as in the original.
    layer, _ = text_layer(text, st["font"], size, st["fill"])
    pad = st["margin"]
    cv = Image.new("RGBA", (layer.size[0] + 2 * pad, layer.size[1] + 2 * pad), (0, 0, 0, 0))
    cv.alpha_composite(layer, (pad, pad))
    return with_shadow(cv, st["shadow"], pad)


def render_chapter(texts, st):
    """``texts`` = [top line, title]: black on transparent, right aligned."""
    cv = Image.new("RGBA", (st["width"], st["height"]), (0, 0, 0, 0))
    for (txt, spec, edge) in ((texts[0], st["top"], st["right"][0]), (texts[1], st["main"], st["right"][1])):
        size = spec["size"]
        hs = spec.get("hscale", 1.0)
        while size > 24 and font(spec["font"], size).getlength(txt) * hs > st["maxw"]:
            hs = max(spec.get("minscale", 1.0), hs * 0.96) if hs > spec.get("minscale", 1.0) else hs
            if font(spec["font"], size).getlength(txt) * hs > st["maxw"] and hs <= spec.get("minscale", 1.0):
                size -= 2
        m = ink_mask(txt, spec["font"], size, spec["baseline"], st["height"], hs)
        cv.alpha_composite(colorize(m, st["fill"]), (edge - m.size[0], 0))
    return cv


def render_mapname(text, st):
    """A subtitle of the world map: capitals, right aligned on a fixed canvas."""
    text = text.upper()
    size = fit_size(text, st, st["size"])
    m = ink_mask(text, st["font"], size, st["baseline"], st["height"], 1.0, st.get("tracking", 0.0))
    cv = Image.new("RGBA", (st["width"], st["height"]), (0, 0, 0, 0))
    cv.alpha_composite(colorize(m, st["fill"]), (st["right"] - m.size[0], 0))
    return cv


def render_chrcopy(parts, st):
    """``parts`` = [(text, 'small' | 'big'), ...] on a common baseline: white with a thick black outline."""
    hs = st["hscale"]

    def build(hs):
        masks = []
        for txt, kind in parts:
            size = st["small"] if kind == "small" else st["big"]
            masks.append(ink_mask(txt, st["font"], size, st["baseline"], st["height"], hs))
        return masks

    masks = build(hs)
    gap = 14
    total = sum(m.size[0] for m in masks) + gap * (len(masks) - 1)
    while total > st["maxw"] and hs > 0.40:
        hs *= 0.97
        masks = build(hs)
        total = sum(m.size[0] for m in masks) + gap * (len(masks) - 1)
    m = Image.new("L", (st["width"], st["height"]), 0)
    x = st["left"]
    for mk in masks:
        m.paste(mk, (x, 0), mk)
        x += mk.size[0] + gap
    ol = m.filter(ImageFilter.MaxFilter(2 * st["olw"] + 1)).filter(ImageFilter.GaussianBlur(1.2))
    out = colorize(ol, st["outline"])
    out.alpha_composite(colorize(m, st["fill"]))
    return out


def render_banner(text, st):
    """A one-line label whose body is set by the height of a reference glyph, as in the original.

    It is compressed horizontally and, if needed, its body is reduced so that it fits in width and height: the accents of
    capitals do not leave through the top, and the tails (g, p, ¡) may be clipped by at most ``clip`` px at the bottom. With
    ``grow`` the canvas grows taller instead of clipping."""
    ref, ref_h = st["ref"]
    size0 = ref_h / cap_ratio(st["font"], ref)
    size, hs = size0, st.get("hscale", 1.0)
    H0, clip = st["height"], st.get("clip", 6)
    for _ in range(12):
        k = size / size0
        layer, up = text_layer(text, st["font"], max(8, round(size)), st["fill"], st.get("stroke", 0) * k,
                               st.get("stroke_fill", (0, 0, 0)), st.get("shear", 0.0), st.get("tracking", 0.0) * k)
        down = layer.size[1] - up
        need = up + max(0, down - clip)
        if need > H0 - 2 and not (st.get("grow") and up <= st["baseline"] - st.get("top", 1)):
            if st.get("grow"):
                size *= (st["baseline"] - st.get("top", 1)) / up * 0.99
            else:
                size *= (H0 - 2) / need * 0.99
            continue
        w = layer.size[0] * hs
        if w <= st["maxw"]:
            break
        hs2 = max(st.get("minscale", 1.0), st["maxw"] / layer.size[0])
        if layer.size[0] * hs2 <= st["maxw"]:
            hs = min(hs, hs2)
            break
        hs = hs2
        size *= st["maxw"] / (layer.size[0] * hs) * 0.99
    layer = layer.resize((max(1, round(layer.size[0] * hs)), layer.size[1]), Image.LANCZOS)
    lw = layer.size[0]
    if st.get("grow"):
        H, base = max(H0, st["baseline"] + down + 2), st["baseline"]
    else:
        H, base = H0, max(up + 1, min(st["baseline"], H0 - 1 - max(0, down - clip)))
    W = st.get("width") or max(st.get("minw", 8), -(-(st["left"] + lw + st.get("pad", 10)) // 8) * 8)
    anchors = {"left": lambda: st.get("left", 0), "right": lambda: st["right"] - lw, "center": lambda: (W - lw) // 2}
    x = anchors[st.get("align", "left")]()
    cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    paste_clip(cv, layer, int(x), base - up)
    return cv


def render_year(text, st, orig):
    """The ``1000year`` picture: keeps the top line (the game's title) of the original and rewrites the bottom one, centred."""
    im = Image.open(io.BytesIO(orig)).convert("RGBA")
    im.paste(Image.new("RGBA", (im.size[0], im.size[1] - st["cut"]), (0, 0, 0, 0)), (0, st["cut"]))
    size = st["size"]
    for _ in range(6):
        layer, up = text_layer(text, st["font"], round(size), st["fill"])
        if layer.size[0] <= st["maxw"]:
            break
        size *= st["maxw"] / layer.size[0] * 0.98
    paste_clip(im, layer, int(st["center"] - layer.size[0] / 2), st["baseline"] - up)
    return im


# ------------------------------------------------------------------------- the poem ---

POEM_LINES = 9                      # the picture is drawn on a grid of 4 px: nine lines of 16 rows each
POEM_GRID = (320, 144)              # the size of that grid; the picture is 4 times larger


def poem_labels(st):
    """The nine English lines of the original poem picture, from its label (joined by ``|``) or from an ``en`` key."""
    english = st.get("en", "").split("|")
    if len(english) != POEM_LINES:
        raise RenderError(
            f"the 'poem' style learns its letters from the original picture, so it needs the {POEM_LINES} English lines of that "
            f"picture joined by '|' as its label (or as an 'en' key in the spec entry); got {len(english)} line(s). "
            "See tools/README.md.")
    return english


def poem_font(orig, english):
    """Glyphs (a 4 px grid, 16 rows per line) cut from the original poem, plus the ones the picture lacks drawn by hand.

    ``english`` are the nine lines of the original, to know which letter each run of ink is. The capital L and E and the vowels
    with an acute accent are not in the picture (the Spanish needs them), so they are drawn here."""
    a = Image.open(io.BytesIO(orig)).convert("RGBA").getchannel("A").point(lambda v: 255 if v > 128 else 0)
    small = a.resize((a.size[0] // 4, a.size[1] // 4), Image.NEAREST)
    px = small.load()
    W = small.size[0]
    glyphs = {}
    for k, text in enumerate(english):
        cols = [any(px[x, y] for y in range(16 * k, 16 * k + 16)) for x in range(W)]
        runs, x = [], 0
        while x < W:
            if cols[x]:
                start = x
                while x < W and cols[x]:
                    x += 1
                runs.append((start, x))
            else:
                x += 1
        letters = [c for c in text if c != " "]
        if len(runs) != len(letters):
            raise RenderError(f"poem line {k + 1}: the picture has {len(runs)} letters but its label has {len(letters)}; "
                              "type the label by hand, spelled exactly as the picture spells it (OCR cannot read this picture)")
        for ch, (x0, x1) in zip(letters, runs):
            glyphs.setdefault(ch, [[1 if px[x, 16 * k + y] else 0 for x in range(x0, x1)] for y in range(16)])

    def block(bars, w):                            # a glyph w columns wide made of bars: (row0, row1, column0, column1)
        g = [[0] * w for _ in range(16)]
        for r0, r1, c0, c1 in bars:
            for y in range(r0, r1):
                for x in range(c0, c1):
                    g[y][x] = 1
        return g

    glyphs["L"] = block([(2, 12, 0, 3), (12, 14, 0, 8)], 8)
    glyphs["E"] = block([(2, 4, 0, 8), (4, 8, 0, 3), (8, 10, 0, 6), (10, 12, 0, 3), (12, 14, 0, 8)], 8)
    for ch, base in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        if base not in glyphs:
            continue
        g = [row[:] for row in glyphs[base]]
        w = len(g[0])
        c = max(0, w - 4)
        for y, (c0, c1) in ((2, (c + 2, c + 4)), (3, (c + 2, c + 4)), (4, (c, c + 2)), (5, (c, c + 2))):
            for x in range(c0, min(c1, w)):
                g[y][x] = 1
        glyphs[ch] = g
    return glyphs


def render_poem(lines, st, orig):
    """The nine lines of the cut-in poem in the picture's own pixel typeface (a 4 px grid, 16 rows per line)."""
    if len(lines) > POEM_LINES:
        raise RenderError(f"the poem picture has room for {POEM_LINES} lines, the text has {len(lines)}")
    glyphs = poem_font(orig, poem_labels(st))
    img = Image.new("L", POEM_GRID, 0)
    px = img.load()
    for k, text in enumerate(lines):
        x = 0
        for ch in text:
            if ch == " ":
                x += 2
                continue
            g = glyphs.get(ch)
            if g is None:
                raise RenderError(f"the poem typeface has no glyph for {ch!r} (line {k + 1})")
            w = len(g[0])
            if x + w > POEM_GRID[0]:
                raise RenderError(f"line {k + 1} of the poem is too wide: {text!r}")
            for y in range(16):
                for i in range(w):
                    if g[y][i]:
                        px[x + i, 16 * k + y] = 255
            x += w + 2
    big = img.resize((POEM_GRID[0] * 4, POEM_GRID[1] * 4), Image.NEAREST)
    return colorize(big, (255, 255, 255))


# ------------------------------------------------------------ interface styles (glow, deco) ---

def render_glow(text, st):
    """A glowing label (title-screen buttons): pale fill, thin outline and a blurred blue halo. The canvas is the ink plus fixed
    margins and the original's height. ``cap`` is the height of a capital in px."""
    size = st["cap"] / cap_ratio(st["font"], st.get("ref", "H"))
    hs = st.get("hscale", 1.0)
    m = ink_mask(text, st["font"], round(size), st["baseline"], st["height"], hs)
    if m.size[0] > st["maxw"]:                          # too wide: compress it down to minscale
        hs = max(st.get("minscale", 0.6), hs * st["maxw"] / m.size[0])
        m = ink_mask(text, st["font"], round(size), st["baseline"], st["height"], hs)
    W = m.size[0] + st["left"] + st["pad"]
    mm = Image.new("L", (W, st["height"]), 0)
    mm.paste(m, (st["left"], 0))
    cv = Image.new("RGBA", (W, st["height"]), (0, 0, 0, 0))
    for r, op, rgb in st["glow"]:
        g = mm.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(r)).point(lambda v, op=op: min(255, int(v * op)))
        cv.alpha_composite(colorize(g, rgb))
    if st.get("outline"):
        cv.alpha_composite(colorize(mm.filter(ImageFilter.MaxFilter(3)), st["outline"]))
    cv.alpha_composite(colorize(mm, st["fill"]))
    return cv


DECO_SMALL = {"de", "del", "la", "el", "los", "las", "y", "a", "en", "para", "con", "o", "of"}


def render_deco(text, st):
    """A screen header (telop) in Art Deco style: the initial of every word heavy and as tall as the canvas, the rest in thin
    small capitals (loose words such as "de" are all small capitals). White on transparent; the canvas is exactly the ink. If
    a small capital carries an accent, all of them drop a size so that the accent fits in the canvas."""
    H = st["height"]
    accent = any(c in "ÁÉÍÓÚÑÜ" for w in text.split() for c in w[1:].upper()) and not st.get("noaccent")
    cap_small = st["capS"] - (st.get("accent_drop", 9) if accent else 0)
    fb = font(st["big"], round(cap_size(st["big"], st["capB"])))
    fb_accent = font(st["big"], round(cap_size(st["big"], H - 24)))         # an accented initial is lower: the accent takes the room above
    fs = font(st["small"], round(cap_size(st["small"], cap_small)))
    hs_big, hs_small = st.get("hsB", 0.55), st.get("hsS", 1.0)

    def build(k):
        x, W = st.get("left", 0), int(sum(fb.size * 1.2 for _ in text)) + 100 + st.get("left", 0)
        cv = Image.new("L", (W, H), 0)

        def put(ch, f, hs, x):
            m = Image.new("L", (int(f.size * 2) + 40, H + 80), 0)
            ImageDraw.Draw(m).text((20, H + 40 - 1 - st.get("bottom", 0)), ch, font=f, fill=255, anchor="ls")
            bb = m.getbbox()
            if not bb:
                return x + int(f.size * 0.28 * hs * k)
            m = m.crop((bb[0], 40, bb[2], H + 40))
            m = m.resize((max(1, round(m.size[0] * hs * k)), H), Image.LANCZOS)
            cv.paste(255, (x, 0), m)
            return x + m.size[0] + round(st.get("gap", 3) * k)

        for w in text.split(" "):
            small = w.lower() in DECO_SMALL
            for i, ch in enumerate(w):
                big = not (i or small)
                face = fs if not big else (fb_accent if ch.upper() in "ÁÉÍÓÚÑÜ" else fb)
                x = put(ch.upper(), face, hs_big if big else hs_small, x)
            x += round(st.get("space", 18) * k)
        bb = cv.getbbox()
        return cv.crop((0, 0, (bb[2] + st.get("left", 0)) if bb else 1, H))

    k = 1.0
    cv = build(k)
    if cv.size[0] > st["maxw"]:                          # too wide: everything is compressed horizontally
        k = max(st.get("minscale", 0.55), st["maxw"] / cv.size[0])
        cv = build(k)
    return colorize(cv, st.get("fill", (240, 240, 240)))


# ----------------------------------------------- generic styles, calibrated on the original ---

def ink_box(text, f, stroke=0, tracking=0.0):
    """(ink width, height above the baseline, height below it, left margin) of the text in the font ``f``."""
    pad = int(f.size) + stroke * 2 + 20
    W = int(f.getlength(text) + tracking * len(text)) + 2 * pad
    m = Image.new("L", (W, int(f.size * 3) + 2 * pad), 0)
    d = ImageDraw.Draw(m)
    base = int(f.size * 1.6) + pad
    if tracking:
        x = float(pad)
        for ch in text:
            d.text((x, base), ch, font=f, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
            x += f.getlength(ch) + tracking
    else:
        d.text((pad, base), text, font=f, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
    bb = m.point(lambda v: 255 if v > 40 else 0).getbbox()
    return (bb[2] - bb[0], base - bb[1], bb[3] - base, bb[0] - pad) if bb else (0, 0, 0, 0)


def measure_fill(im):
    """Mean colour (RGB) of the opaque pixels of the original picture."""
    px = im.load()
    s = [0, 0, 0]
    n = 0
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b, a = px[x, y]
            if a >= 230:
                s[0] += r
                s[1] += g
                s[2] += b
                n += 1
    return tuple(round(v / n) for v in s) if n else (240, 240, 240)


def calibrate(st, ow, oh):
    """With the English text ``en``, return (body, horizontal compression, descent below the baseline) so that the English
    would take exactly ``ow`` x ``oh`` px of ink in the font and with the effects of ``st``."""
    stroke, track = st.get("stroke", 0), st.get("tracking", 0.0)
    if st.get("size"):                                   # a body given by hand (the two-line labels of the original, say)
        return st["size"], st.get("hscale", 1.0), 0
    size = 100.0
    for _ in range(3):
        f = font(st["font"], max(6, round(size)))
        w, up, down, lb = ink_box(st["en"], f, stroke, track)
        size = size * oh / max(1, up + down)
    size = max(6, round(size))
    f = font(st["font"], size)
    w, up, down, lb = ink_box(st["en"], f, stroke, track)
    hs = st.get("hscale") or max(0.45, min(1.4, ow / max(1, w)))
    return size, hs, down


def text_for(text, st, size, hs, fill, maxw):
    """The RGBA layer of the new text at the calibrated body and compression; wider than ``maxw`` it is compressed more."""
    t = text.upper() if st.get("upper") else text
    layer, upl = text_layer(t, st["font"], size, fill, st.get("stroke", 0), st.get("stroke_fill", (0, 0, 0)),
                            st.get("shear", 0.0), st.get("tracking", 0.0))
    lw = max(1, round(layer.size[0] * hs))
    if lw > maxw:
        hs2 = max(st.get("minscale", 0.55), maxw / layer.size[0])
        hs = min(hs, hs2) if st.get("hscale") is None else hs2
        lw = max(1, round(layer.size[0] * hs))
    out = layer.resize((lw, layer.size[1]), Image.LANCZOS)
    if st.get("shrink") and lw > maxw:                   # even compressed to the minimum it does not fit: shrink it all alike
        k = maxw / lw
        out = out.resize((max(1, round(lw * k)), max(1, round(out.size[1] * k))), Image.LANCZOS)
        upl = round(upl * k)
    return out, upl


def render_auto(text, st, orig):
    """Rewrite a label by measuring the original: with the English text (``en``) it calibrates the body, the horizontal
    compression, the baseline and the margins so that the English would take exactly the original's ink, and applies the same
    to the new text.

    st: font, en, [fill], [stroke, stroke_fill], [hscale], [tracking], [align left|center|right], [maxw], [minscale], [upper],
        [shadow], [thr] (alpha threshold of the solid body), [tail_glyph] (keeps the last glyph of the original, a star
        say), [clip]."""
    im0 = Image.open(io.BytesIO(orig)).convert("RGBA")
    W0, H0 = im0.size
    thr = st.get("thr", 128)                             # alpha threshold of the solid body (leaves out halos and shadows)
    a = im0.getchannel("A").point(lambda v: 255 if v > thr else 0)
    bb = a.getbbox()
    tail = None
    if st.get("tail_glyph"):                             # the last glyph of the original (a star, say) is kept as it is
        apx = a.load()
        cols = [any(apx[x, y] for y in range(a.size[1])) for x in range(a.size[0])]
        x1 = max(i for i, c in enumerate(cols) if c)
        x0 = x1
        while x0 > 0 and cols[x0 - 1]:
            x0 -= 1
        tail = im0.crop((max(0, x0 - 2), 0, min(a.size[0], x1 + 3), a.size[1]))
        bb = a.crop((0, 0, max(0, x0 - 2), a.size[1])).getbbox() or bb
        st = dict(st)
        st["en"] = st["en"].rstrip("★")
        text = text.rstrip("★")
    if bb is None:
        raise RenderError(f"the original picture has no ink above the alpha threshold {thr}")
    ow, oh = bb[2] - bb[0], bb[3] - bb[1]
    size, hs, down = calibrate(st, ow, oh)
    base_y = bb[3] - down                                # baseline of the original (px of the original canvas)
    left, right_margin = bb[0], W0 - bb[2]
    fill = st.get("fill") or measure_fill(im0)
    maxw = st.get("maxw") or max(int(ow * 1.6), ow + 160)
    layer, upl = text_for(text, st, size, hs, fill, maxw)
    lw = layer.size[0]
    dn = layer.size[1] - upl
    extra_top, extra_bot = max(0, upl - base_y), max(0, (base_y + dn) - H0 - st.get("clip", 0))
    if extra_top:
        extra_top += 1                                   # one pixel of margin so the ink does not touch the edge
    if extra_bot:
        extra_bot += 2                                   # a margin so the ink does not touch the bottom edge
    if st.get("shadow"):
        extra_bot += int(st["shadow"][3] + st["shadow"][0])    # room for the shifted shadow (it would be cut at the edge)
    tw = (tail.size[0] + 4) if tail is not None else 0
    W = lw + tw + left + right_margin
    align = st.get("align", "left")
    if align != "left":
        W = max(W0, lw + tw + 2)                         # the canvas keeps its original width if the text fits
    cv = Image.new("RGBA", (W, H0 + extra_top + extra_bot), (0, 0, 0, 0))
    x = {"left": left, "right": W - right_margin - lw - tw, "center": (W - lw - tw) // 2}[align]
    paste_clip(cv, layer, int(x), base_y + extra_top - upl)
    if tail is not None:
        paste_clip(cv, tail, int(x) + lw + 4, extra_top)
    if st.get("shadow"):
        cv = with_shadow(cv, st["shadow"], 4)
    return cv


def render_lines(text, st, orig):
    """A label of several lines (separated by ``|`` both in ``texto`` and in the English calibration text ``en``): it finds the
    bands of ink of the original, calibrates and writes every line with ``render_auto`` on its band, and stacks them keeping
    the original separations."""
    im = Image.open(io.BytesIO(orig)).convert("RGBA")
    W, H = im.size
    thr = st.get("thr", 128)
    a = im.getchannel("A").point(lambda v: 255 if v > thr else 0)
    px = a.load()
    rows = [any(px[x, y] for x in range(W)) for y in range(H)]
    bands, y = [], 0
    while y < H:
        if rows[y]:
            y0 = y
            while y < H and rows[y]:
                y += 1
            if bands and y0 - bands[-1][1] < st.get("gap", 3):
                bands[-1] = (bands[-1][0], y)
            else:
                bands.append((y0, y))
        else:
            y += 1
    es, en = text.split("|"), st["en"].split("|")
    if len(bands) < len(es):                             # lines that touch (tight leading): cut at the minima of the ink profile
        ink = [sum(1 for x in range(W) if px[x, y]) for y in range(H)]
        smooth = [sum(ink[max(0, y - 3):y + 4]) for y in range(H)]
        first = next(y for y in range(H) if rows[y])
        last = max(y for y in range(H) if rows[y])
        n = len(es)
        cuts = []
        for k in range(1, n):
            a0 = first + (last - first) * (2 * k - 1) // (2 * n)
            a1 = first + (last - first) * (2 * k + 1) // (2 * n)
            cuts.append(min(range(a0, a1), key=lambda y: smooth[y]))
        edges = [first] + cuts + [last + 1]
        bands = list(zip(edges[:-1], edges[1:]))
    if len(bands) != len(es) or len(es) != len(en):
        raise RenderError(f"{len(bands)} bands of ink in the original, {len(es)} lines in the text, {len(en)} in the English label")
    pad = st.get("pad", 8)
    outs = []
    for (y0, y1), t, e in zip(bands, es, en):
        c0, c1 = max(0, y0 - pad), min(H, y1 + pad)
        buf = io.BytesIO()
        im.crop((0, c0, W, c1)).save(buf, "WEBP", lossless=True)
        sub = dict(st, en=e)
        sub["thr"] = thr
        outs.append((c0, render_auto(t, sub, buf.getvalue())))
    top = outs[0][0]
    Wn = max(o.size[0] for _, o in outs)
    shift, canvas_h = 0, 0
    placed = []
    for i, (c0, o) in enumerate(outs):
        y = c0 - top + shift
        placed.append((y, o))
        extra = o.size[1] - (min(H, bands[i][1] + pad) - c0)
        shift += max(0, extra)
        canvas_h = max(canvas_h, y + o.size[1])
    cv = Image.new("RGBA", (Wn, canvas_h), (0, 0, 0, 0))
    for y, o in placed:
        cv.alpha_composite(o, (0, max(0, y)))
    return cv


def erase_region(im, st):
    """Erase the ``clear`` area of a picture with a panel: ``interp`` (interpolate between the rows above and below; panels with a
    vertical gradient), ``rowcopy`` (copy into every row the pixel of the given column; buttons with horizontal stripes) or
    ``transparent`` (alpha 0)."""
    x0, y0, x1, y1 = st["clear"]
    px = im.load()
    mode = st.get("erase", "interp")
    for y in range(y0, y1):
        for x in range(x0, x1):
            if mode == "rowcopy":
                px[x, y] = px[st["rowcopy"], y]
            elif mode == "transparent":
                px[x, y] = (0, 0, 0, 0)
            else:
                t = (y - y0) / max(1, y1 - y0 - 1)
                top, bot = px[x, max(0, y0 - 2)], px[x, min(im.size[1] - 1, y1 + 2)]
                px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bot))


def render_patch(text, st, orig):
    """Text inside a picture that has to stay (a panel, button or icon): erase the ``clear`` area and write the new text,
    calibrated on the original ink box ``tbox`` = (x0, y0, x1, y1). ``align``: center (the default, on the centre of ``tbox``),
    left or right. The canvas grows if the text does not fit (``grow``: 'right' | 'left')."""
    im = Image.open(io.BytesIO(orig)).convert("RGBA")
    erase_region(im, st)
    tb = st["tbox"]
    ow, oh = tb[2] - tb[0], tb[3] - tb[1]
    size, hs, down = calibrate(st, ow, oh)
    base_y = st.get("base") or tb[3] - down
    layer, upl = text_for(text, st, size, hs, st["fill"], st.get("maxw") or max(int(ow * 1.3), ow + 40))
    lw = layer.size[0]
    if st.get("shrink") and layer.size[1] < oh + 2 * st.get("stroke", 0) + 12 and upl < layer.size[1]:    # centre the reduced text vertically
        dn_l = layer.size[1] - upl
        base_y = round((tb[1] + tb[3]) / 2 - (dn_l - upl) / 2)
    align = st.get("align", "center")
    x = {"center": (tb[0] + tb[2] - lw) // 2, "left": tb[0], "right": tb[2] - lw}[align]
    pad_l = max(0, -x)
    pad_r = max(0, x + lw - im.size[0]) if st.get("grow") else 0
    if pad_l or pad_r:
        cv = Image.new("RGBA", (im.size[0] + pad_l + pad_r, im.size[1]), (0, 0, 0, 0))
        cv.alpha_composite(im, (pad_l, 0))
        im = cv
        x += pad_l
    paste_clip(im, layer, int(x), base_y - upl)
    if st.get("shadow"):
        im = with_shadow(im, st["shadow"], 4)
    return im


# --------------------------------------------------------------------- the style table ---

_GLOW_N = [(6, 0.7, (45, 125, 215)), (2.5, 0.6, (60, 150, 225))]
_GLOW_S = [(8, 1.0, (140, 190, 255)), (3, 0.8, (200, 230, 255))]
STYLES.update({
    # Title-menu buttons (normal and selected): heavy teal serif with a blue glow.
    "titlebtn":     dict(kind="glow", font="georgia_bold", cap=47, fill=(73, 192, 213), glow=_GLOW_N, outline=(30, 110, 160), height=97,
                         baseline=73, left=24, pad=14, hscale=0.88, minscale=0.6, maxw=600),
    "titlebtn_sel": dict(kind="glow", font="georgia_bold", cap=49, fill=(222, 236, 250), glow=_GLOW_S, outline=(70, 140, 215), height=109,
                         baseline=82, left=28, pad=14, hscale=0.88, minscale=0.6, maxw=600),
    # Screen headers (telop): Art Deco, a heavy full-height initial and thin small capitals.
    "telop":        dict(kind="deco", big="futura_cexb", small="avenir_cond", capB=107, capS=92, height=105, hsB=0.75, hsS=1.0,
                         gap=3, space=18, maxw=1100, minscale=0.55),
    # Headers of the Extra mode (ex_*): squared "technical" face, white, lower case.
    "telop_ex":     dict(kind="banner", font="krungthep", ref=("H", 69), fill=(224, 224, 224), height=92, baseline=70, left=0, pad=0,
                         hscale=1.0, minscale=0.7, maxw=1100, tracking=2.0),
    # The empty-slot label of the save screen: translucent grey panel with dark text in a squared face.
    "nodata":       dict(kind="patch", font="krungthep", fill=(64, 64, 64), clear=(92, 110, 388, 184), erase="interp",
                         tbox=(104, 121, 375, 171), maxw=290, tracking=1.0),
    # Generic styles: every parameter goes in the spec entry (font, `en`, fill, outline, boxes...).
    "auto":         dict(kind="auto"),
    "patch":        dict(kind="patch"),
    "lines":        dict(kind="lines"),
    # Flat labels calibrated on the original (render_auto): one typeface per family; the compression comes from the English.
    "flat_tahoma":  dict(kind="auto", font="tahoma"),
    "flat_gill":    dict(kind="auto", font="gill"),
    "flat_trebu":   dict(kind="auto", font="trebuchet"),
    "flat_krung":   dict(kind="auto", font="krungthep"),
    # Skill names (skillname/*.webp): white condensed face with a black outline and a soft shadow.
    "skillname":    dict(kind="auto", font="din_cond", stroke=4, stroke_fill=(0, 0, 0), fill=(255, 255, 255), shadow=(3, 0.6, 2, 3), thr=200),
    # Dungeon event notices (evShotNN): serif italic, white, no outline, left aligned.
    "evshot":    dict(kind="banner", font="tnr_italic", ref=("I", 70), fill=(255, 255, 255), stroke=1.0, stroke_fill=(255, 255, 255), hscale=0.95, minscale=0.80,
                      height=96, baseline=79, left=5, maxw=1100),
    # Escape result (escapeShot): script face in light grey, flush right on a canvas of 704.
    "escape":    dict(kind="banner", font="georgia_bi", ref=("l", 86), fill=(240, 240, 240), hscale=1.12, height=96, width=704,
                      align="right", right=691, baseline=88, maxw=660, minscale=0.8),
    # Prompts of the button-pressing mini-games (at_textN): rounded face with a thick black outline.
    "atprompt":  dict(kind="banner", font="arial_rounded", ref=("E", 63), fill=(240, 240, 240), stroke=5, hscale=1.13, minscale=0.80,
                      height=96, baseline=84, left=9, maxw=1000),
    "atcaption": dict(kind="banner", font="impact", ref=("l", 106), fill=(240, 240, 240), stroke=6, shear=0.22, hscale=1.03, minscale=0.80,
                      grow=True, height=128, width=1408, baseline=119, left=9, maxw=1390),
    # Large area names (largeNameN): tall serif italic with an outline.
    "largename": dict(kind="banner", font="tnr_bolditalic", ref=("H", 75), fill=(255, 255, 255), stroke=4, hscale=0.84, minscale=0.60,
                      height=96, baseline=87, left=2, maxw=1000),
    "newskill":  dict(kind="banner", font="impact", ref=("N", 96), fill=(255, 255, 255), stroke=7, height=128, width=384,
                      baseline=113, left=11, maxw=370, minscale=0.70),
    "unknown":   dict(kind="banner", font="impact", ref=("N", 73), fill=(255, 255, 255), hscale=1.2, height=96, width=512, baseline=79,
                      left=7, maxw=495, minscale=0.70),
    "noskill":   dict(kind="banner", font="impact", ref=("N", 136), fill=(255, 255, 255), stroke=8, height=160, width=512,
                      baseline=150, left=6, maxw=500, minscale=0.70),
    "stageclear": dict(kind="banner", font="optima", ref=("E", 122), fill=(255, 255, 255), stroke=3, stroke_fill=(60, 60, 50),
                       height=288, width=1152, align="center", baseline=205, maxw=1100, minscale=0.8),
    "year":      dict(font="chancery", size=70, fill=(255, 255, 255), cut=150, center=387, baseline=228, maxw=690),
})

#: Style -> the function that draws it.
RENDER = {"story": render_story, "title": render_script, "caption": render_script, "chapter": render_chapter,
          "mapname": render_mapname, "chrcopy": render_chrcopy, "year": render_year, "poem": render_poem}
STYLES["poem"] = {}
_BY_KIND = {"banner": render_banner, "glow": render_glow, "deco": render_deco, "patch": render_patch,
            "auto": render_auto, "lines": render_lines}
for _name, _preset in list(STYLES.items()):
    if _preset.get("kind") == "banner":
        # Banners grow taller instead of clipping the tails (g, p, y, ¡): the canvas extends downwards.
        _preset.setdefault("grow", True)
    if _preset.get("kind") in _BY_KIND:
        RENDER[_name] = _BY_KIND[_preset["kind"]]

#: The renderers that also read the original picture (the others draw on an empty canvas).
USES_ORIGINAL = {render_year, render_poem, render_patch, render_auto, render_lines}


# ------------------------------------------------------------------ specs, labels, packages ---

def load_labels(path: Path) -> dict:
    """``{package: {entry: English text}}`` from the calibration labels, or ``{}`` when the file does not exist."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"{path}: cannot read the calibration labels: {exc}") from exc


def merge_specs(paths) -> dict:
    """The specs merged by package; for the same entry the last spec wins."""
    spec: dict = {}
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RenderError(f"{path}: cannot read the spec: {exc}") from exc
        for package, items in data.items():
            spec.setdefault(package, {}).update(items)
    return spec


def draw(entry: dict, label: str, original: bytes, where: str, labels_path: Path):
    """Draw one picture from its spec entry. ``label`` is the English calibration text of the original (maybe empty)."""
    style = entry.get("estilo")
    if style not in STYLES:
        raise RenderError(f"{where}: unknown style {style!r}; the known ones are: {', '.join(sorted(STYLES))}")
    if "texto" not in entry:
        raise RenderError(f"{where}: the entry has no 'texto'")
    st = dict(STYLES[style])
    st.setdefault("en", label)                           # an "en" key of the entry overrides the label
    st.update({k: (tuple(v) if isinstance(v, list) else v) for k, v in entry.items() if k not in ("estilo", "texto")})
    render = RENDER[style]
    calibrates = render is render_lines or (render in (render_auto, render_patch) and not st.get("size"))
    if calibrates and not st.get("en"):                  # (the poem checks its own label: it needs nine lines)
        raise RenderError(f"{where}: the style {style!r} calibrates on the English text of the original picture, and there is none. "
                          f"Put it in the labels file ({labels_path}; see tools/README.md) or in an 'en' key of the entry.")
    try:
        if render in USES_ORIGINAL:
            return render(entry["texto"], st, original)
        return render(entry["texto"], st)
    except RenderError as exc:
        raise RenderError(f"{where}: {exc}") from exc


def run(originals: Path, specs, out: Path, labels_path: Path) -> int:
    spec = merge_specs(specs)
    labels = load_labels(labels_path)
    pictures = 0
    for package, items in spec.items():
        source = originals / "data" / package
        if not source.is_file():
            raise RenderError(f"{source} does not exist: --originals must be the folder that holds data/ as 'python rpl.py unpack' "
                              f"writes it, and it must have {package}")
        destination = out / "data" / package
        destination.parent.mkdir(parents=True, exist_ok=True)
        if package.lower().endswith(".webp"):            # a loose picture, not a package: the spec is the entry itself
            blob = encode_webp(draw(items, labels.get("", {}).get(package, ""), source.read_bytes(), package, labels_path))
            destination.write_bytes(blob)
            print(f"{package} -> {destination}")
            pictures += 1
            continue
        data0, entries = read_pck(source.read_bytes())
        index = {}
        for ent in entries:
            index.setdefault(entry_name(ent[0]), ent)
        for name, entry in items.items():
            if name not in index:
                raise RenderError(f"{package} has no picture called {name}")
            ent = index[name]
            label = labels.get(package, {}).get(name, "")
            ent[1] = encode_webp(draw(entry, label, ent[1], f"{package}/{name}", labels_path))
        destination.write_bytes(write_pck(data0, entries))
        print(f"{package}: {len(items)} pictures -> {destination}")
        pictures += len(items)
    print(f"{pictures} pictures in {len(spec)} packages")
    return 0


def build_parser() -> argparse.ArgumentParser:
    work = user_dir() / "work" / "switch"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--originals", type=Path, default=work / "data_en", metavar="DIR",
                    help="the unpacked data_en.bin, a folder holding data/event/*.pck and data/System/*.pck (default: work/switch/data_en)")
    ap.add_argument("--spec", type=Path, action="append", required=True, metavar="FILE",
                    help="a render spec; repeat the option to merge several (the last one wins)")
    ap.add_argument("--out", type=Path, default=work / "rendered", metavar="DIR",
                    help="where to write the new packages, as <DIR>/data/... (default: work/switch/rendered)")
    ap.add_argument("--labels", type=Path, default=work / "ocr" / "en_labels.json", metavar="PATH",
                    help="the English text of the original pictures, {package: {entry: text}}; it is game text, keep it under work/ "
                         "(default: work/switch/ocr/en_labels.json)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args.originals, args.spec, args.out, args.labels)
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
