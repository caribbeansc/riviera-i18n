#!/usr/bin/env python3
"""Draw the Android pictures the Switch dump cannot give, and store them as the files of a language pack.

Development tool (it uses the fonts of the machine it runs on; the pack stores the result, so users never need those fonts). The Android app
has screens Switch does not (the options screen's "Wide screen", the cloud-backup screen, the voice-language buttons, the focus label...) and
the pictures of those say something in Japanese. For each of them this tool draws the label of the language, measuring the size, the position
and the colour from the user's Android original, and writes it into ``langs/<code>/android/images/`` in the form that keeps the game's
artwork out of the repository (see :mod:`riviera.android.images`):

``full``
    text on an empty transparent canvas of the size of the original;
``delta``
    the original has art that stays (the arrows and bars of the backup screen): only the changed pixels are stored;
``layer``
    the picture mixes our text with a piece of the original (the speaker of the voice buttons, the MOVE word of the mode label): the text layer
    is stored and the piece is copied from the user's own picture when the app is built.

    python tools/android/render_images.py --lang es --apk-dir /path/to/apks [--work build/render]

The result is checked by building the app and comparing it with the pictures this tool made (tests/test_android_images.py has the synthetic
checks; the byte-for-byte check against a reference build is documented in docs/ANDROID.md).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riviera import images as swimages              # noqa: E402
from riviera.android import images as aimages       # noqa: E402
from riviera.android.assets import AndroidAssets    # noqa: E402

F = "/System/Library/Fonts/"
S = F + "Supplemental/"
FONTS = {"rounded": (S + "Arial Rounded Bold.ttf", 0), "avenir_cond": (F + "Avenir Next Condensed.ttc", 7), "impact": (S + "Impact.ttf", 0),
         "tahoma": (S + "Tahoma.ttf", 0), "din_cond": (S + "DIN Condensed Bold.ttf", 0), "arial_black": (S + "Arial Black.ttf", 0)}
VOICE_FONTS = [S + "Arial Narrow Bold.ttf", S + "Arial Bold.ttf", F + "HelveticaNeue.ttc"]

#: What each language writes. Everything but the options explanation is English in every pack (menus, labels and names stay in English).
TEXTS = {
    "en": {"wide_help": "With ON, the screen widens to fit the device."},
    "es": {"wide_help": "Con ON, la pantalla se ensancha para ajustarse al dispositivo."},
}
COMMON = {
    "wide": "Wide screen", "focus": "FOCUS", "skill": "Sorcery Wave", "look": "LOOK",
    "voice": {"text_EN.webp": "English", "text_JP.webp": "Japanese"},
    "backup_bars": {"backup_data_cloud.webp": "Cloud data", "backup_data_now.webp": "Current data"},
    "backup_arrows": {"backup_backup_button.webp": (["Back up", "data"], 0.74, 12), "backup_dataload_button.webp": (["Load", "data"], 0.8, 0)},
    "backup_labels": {"backup_clear.webp": "Cleared", "backup_no_clear.webp": "Not cleared", "backup_nodata.webp": "No data",
                      "backup_item_count.webp": "Items obtained", "backup_save_count.webp": "Save data count", "backup_day.webp": "Last saved"},
}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path, index = FONTS[name]
    return ImageFont.truetype(path, size, index=index)


def ink(im, thr=24):
    return im.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox()


def median_color(im, thr=200):
    """Mean colour of the nearly opaque pixels (the fill of the letters)."""
    px = im.load()
    s, n = [0, 0, 0], 0
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b, a = px[x, y]
            if a >= thr:
                s[0] += r
                s[1] += g
                s[2] += b
                n += 1
    return tuple(round(v / n) for v in s) if n else (240, 240, 240)


def text_layer(lines, fname, size, fill, outline=None, ow=0, tracking=0.0, spacing=1.0):
    """RGBA layer with the text (one or several centred lines) and, if asked for, an outline of ``ow`` px; cropped to the ink."""
    f = font(fname, size)
    pad = ow + 6
    ws = [int(f.getlength(t)) + int(tracking * len(t)) for t in lines]
    lh = int(size * 1.25 * spacing)
    W, H = max(ws) + 2 * pad, lh * len(lines) + 2 * pad
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    om = Image.new("L", (W, H), 0)
    od = ImageDraw.Draw(om)
    for i, t in enumerate(lines):
        x = pad + (max(ws) - ws[i]) // 2
        y = pad + i * lh
        if tracking:
            for ch in t:
                d.text((x, y), ch, font=f, fill=255)
                od.text((x, y), ch, font=f, fill=255, stroke_width=ow, stroke_fill=255)
                x += f.getlength(ch) + tracking
        else:
            d.text((x, y), t, font=f, fill=255)
            od.text((x, y), t, font=f, fill=255, stroke_width=ow, stroke_fill=255)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if outline and ow:
        out.paste(Image.new("RGBA", (W, H), outline + (255,)), (0, 0), om)
    out.paste(Image.new("RGBA", (W, H), tuple(fill) + (255,)), (0, 0), m)
    bb = out.getchannel("A").getbbox()
    return out.crop(bb) if bb else out


def ink_text_layer(text, fname, size, fill, stroke=0, stroke_fill=(0, 0, 0)):
    """RGBA layer cropped to the ink (with an outline), as the banner renderer draws a skill name."""
    f = font(fname, size)
    stroke = int(round(stroke))
    pad = int(size * 0.5) + stroke + 10
    wn = int(f.getlength(text)) + 2 * pad
    base = pad + int(size * 1.0)
    m = Image.new("RGBA", (wn, base + int(size * 0.7) + pad), (0, 0, 0, 0))
    ImageDraw.Draw(m).text((pad, base), text, font=f, fill=fill, anchor="ls", stroke_width=stroke, stroke_fill=stroke_fill)
    bb = m.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    return m.crop(bb) if bb else Image.new("RGBA", (1, 1), (0, 0, 0, 0))


def cap_size(fname: str, cap: float) -> float:
    """Body size (px) with which the "H" of the font is ``cap`` px tall."""
    f = font(fname, 200)
    bb = f.getbbox("H", anchor="ls")
    return 200.0 * cap / (bb[3] - bb[1])


def with_shadow(layer, shadow, pad):
    """Blurred black shadow under an RGBA layer (``shadow`` = radius, opacity, dx, dy)."""
    r, op, dx, dy = shadow
    a = layer.getchannel("A").filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v * op))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a)
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (dx, dy))
    out.alpha_composite(layer)
    return out


def soft_shadow(im, dx=2, dy=2, blur=2, alpha=0.6):
    """Soft shadow under the layer (the canvas grows)."""
    pad = blur * 3 + max(dx, dy)
    cv = Image.new("RGBA", (im.size[0] + 2 * pad, im.size[1] + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (pad + dx, pad + dy), im.getchannel("A"))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    sh.putalpha(sh.getchannel("A").point(lambda v: int(v * alpha)))
    cv.alpha_composite(sh)
    cv.alpha_composite(im, (pad, pad))
    return cv


def paste_clip(cv, layer, x, y):
    tmp = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    tmp.paste(layer, (x, y))
    cv.alpha_composite(tmp)


def place(canvas_size, layer, align="left", left=None, vcenter=None, right_pad=0):
    """Paste ``layer`` on a transparent canvas: aligned left (at ``left``), centred or right; centred vertically on ``vcenter``."""
    W, H = canvas_size
    cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = {"left": left or 0, "center": (W - layer.size[0]) // 2, "right": W - layer.size[0] - right_pad}[align]
    y = (vcenter if vcenter is not None else H / 2) - layer.size[1] / 2
    if x >= 0 and y >= 0:
        cv.alpha_composite(layer, (int(x), int(round(y))))
    else:
        paste_clip(cv, layer, int(x), int(round(y)))
    return cv


def fit_width(layer, maxw, minscale=0.8):
    """If the layer is wider than ``maxw`` it is squeezed horizontally down to ``minscale`` and, if it still does not fit, reduced evenly."""
    if layer.size[0] <= maxw:
        return layer
    k = maxw / layer.size[0]
    if k >= minscale:
        return aimages.resize(layer, (maxw, layer.size[1]))
    layer = aimages.resize(layer, (round(layer.size[0] * minscale), layer.size[1]))
    k2 = maxw / layer.size[0]
    return aimages.resize(layer, (maxw, round(layer.size[1] * k2)))


def gen_label(a_im, text, fname, size_k=0.85, fill=None, outline=None, ow=0, shadow=None, align="left", tracking=0.0):
    """One-line label with the measures of the Japanese Android picture: same canvas height, ink at the height of the original's."""
    bb = ink(a_im) or (0, 0) + a_im.size
    fill = fill or median_color(a_im)
    h_ink = bb[3] - bb[1]
    f0 = font(fname, 100)
    cap = f0.getbbox("H")[3] - f0.getbbox("H")[1]
    size = max(8, round(100 * size_k * h_ink / cap))                    # body: the capitals are about size_k of the Japanese ink
    layer = text_layer([text], fname, size, fill, outline, ow, tracking)
    if shadow:
        layer = soft_shadow(layer, *shadow)
    layer = fit_width(layer, a_im.size[0] - bb[0] - 1 if align == "left" else a_im.size[0] - 2, 0.8)
    return place(a_im.size, layer, align, left=bb[0], vcenter=(bb[1] + bb[3]) / 2)


def gen_backup_bars(a_im, text, fname="rounded", size_k=0.8, fill=(240, 240, 240)):
    """"| Cloud data |": the bars of the original (isolated ink columns at both ends) stay and the text is centred between them.
    Returns ``(picture, [x range of each bar], text layer, position of the layer)``."""
    W, H = a_im.size
    a = a_im.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    px = a.load()
    cols = [any(px[x, y] for y in range(H)) for x in range(W)]
    runs, x = [], 0
    while x < W:
        if cols[x]:
            s = x
            while x < W and cols[x]:
                x += 1
            runs.append((s, x))
        else:
            x += 1
    bars = [r for r in runs if r[1] - r[0] <= 6]
    left_bar, right_bar = bars[0], bars[-1]
    cv = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for r in (left_bar, right_bar):
        cv.alpha_composite(a_im.crop((r[0], 0, r[1], H)), (r[0], 0))
    inner0, inner1 = left_bar[1] + 8, right_bar[0] - 8
    ys = [y for x in range(left_bar[0], left_bar[1]) for y in range(H) if px[x, y]]
    cy = (min(ys) + max(ys)) / 2 if ys else H / 2
    tb = [(x0, x1) for x0, x1 in runs if left_bar[1] < x0 and x1 < right_bar[0]]
    ys2 = [y for x0, x1 in tb for x in range(x0, x1) for y in range(H) if px[x, y]]
    h_ink = (max(ys2) - min(ys2)) if ys2 else H * 0.6
    f0 = font(fname, 100)
    cap = f0.getbbox("H")[3] - f0.getbbox("H")[1]
    layer = text_layer([text], fname, max(8, round(100 * size_k * h_ink / cap)), fill)
    layer = fit_width(layer, inner1 - inner0, 0.8)
    pos = (inner0 + (inner1 - inner0 - layer.size[0]) // 2, int(round(cy - layer.size[1] / 2)))
    paste_clip(cv, layer, *pos)
    return cv, [left_bar, right_bar], layer, pos


def gen_arrow(a_im, lines, fname="rounded", scale=0.78, dy=0):
    """Arrow button of the backup screen: the Japanese text is erased from the body of the arrow (aimages.erase_enclosed, which the build
    repeats on the user's own picture, so nothing of it is stored) and the English goes in two lines.
    Returns ``(picture, text layer, position of the layer)``."""
    a, (x0, y0, x1, y1) = aimages.erase_enclosed(a_im)
    body = Counter(a.getpixel((x, y))[:3] for y in range(a.size[1]) for x in range(a.size[0])
                   if a.getpixel((x, y))[3] > 250 and 60 < sum(a.getpixel((x, y))[:3]) / 3 < 215).most_common(1)[0][0]
    h_text, w_text = y1 - y0 + 1, x1 - x0 + 1
    layer = text_layer(lines, fname, max(10, round(h_text / (len(lines) * 1.2) * scale)), (255, 255, 255),
                       outline=tuple(int(c * 0.6) for c in body), ow=2)
    layer = fit_width(layer, w_text + 8, 0.85)
    pos = (int((x0 + x1 - layer.size[0]) / 2), int((y0 + y1 - layer.size[1]) / 2) + dy)
    paste_clip(a, layer, *pos)
    return a, layer, pos


# ----------------------------------------------------------- voice buttons --

def voice_icon_box(im: Image.Image):
    """Box of the loudspeaker of a voice button: the last group of light columns, separated from the text by a gap."""
    a = im.convert("RGBA")
    w, h = a.size
    white = [any(a.getpixel((x, y))[3] > 128 and sum(a.getpixel((x, y))[:3]) > 600 for y in range(h)) for x in range(w)]
    x = w - 1
    while x >= 0 and not white[x]:
        x -= 1
    right = x
    gap = 0
    while x >= 0 and (white[x] or gap < 8):
        gap = 0 if white[x] else gap + 1
        x -= 1
    left = x + gap + 1
    return max(0, left - 6), 0, min(w, right + 7), h


def voice_font(size: int) -> ImageFont.FreeTypeFont:
    path = next((p for p in VOICE_FONTS if Path(p).exists()), None)
    if path is None:
        sys.exit("none of the fonts of the voice buttons was found: " + ", ".join(VOICE_FONTS))
    return ImageFont.truetype(path, size)


def voice_layer(label: str, icon_w: int, orig_w: int):
    """``(text layer, x of the layer on the canvas, x of the loudspeaker on the canvas)``: the label with a soft glow, as wide as possible without
    deforming the loudspeaker, centred in the canvas of the original."""
    h, gap = 88, 10
    for size in range(52, 30, -1):
        f = voice_font(size)
        d = ImageDraw.Draw(Image.new("L", (1, 1)))
        tw = int(d.textlength(label, font=f))
        w = tw + gap + icon_w + 16
        if w <= orig_w:
            break
    if w > orig_w:
        sys.exit(f"the label {label!r} does not fit its button")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((8, h // 2 + 2), label, font=f, fill=255, anchor="lm")
    glow = mask.filter(ImageFilter.GaussianBlur(3)).point(lambda v: min(255, v * 2))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (w, h), (205, 255, 255, 255)), (0, 0), glow)
    out.paste(Image.new("RGBA", (w, h), (245, 255, 255, 255)), (0, 0), mask)
    x = (orig_w - w) // 2
    return out, x, x + 8 + tw + gap


def trigger_layer(original: Image.Image, text: str):
    """``(cut, text layer)`` of the mode label picture: the top row (MOVE) is kept and the bottom row is drawn again."""
    rows = [any(original.getpixel((x, y))[3] > 40 for x in range(original.width)) for y in range(original.height)]
    gaps = [y for y in range(20, original.height - 20) if not rows[y]]
    cut = gaps[len(gaps) // 2] if gaps else original.height // 2           # the gap between the two rows
    f = ImageFont.truetype(FONTS["arial_black"][0], 92)
    txt = Image.new("RGBA", (original.width, original.height - cut), (0, 0, 0, 0))
    ImageDraw.Draw(txt).text((original.width // 2, (original.height - cut) // 2), text, font=f, fill=(255, 255, 255, 255), anchor="mm",
                             stroke_width=10, stroke_fill=(0, 0, 0, 255))
    return cut, txt


# ------------------------------------------------------------------- pack --

class Writer:
    """Writes the pictures and the manifest of ``langs/<code>/android/images/``."""

    def __init__(self, out: Path):
        self.out = out
        self.entries: dict[str, dict[str, dict]] = {}
        self.expect: dict[tuple[str, str], Image.Image] = {}           # the picture each layer entry must compose to (checked in verify)
        out.mkdir(parents=True, exist_ok=True)
        for old in list(out.glob("*.webp")) + list(out.glob("*.png")):
            old.unlink()

    def stem(self, package: str, key: str) -> str:
        name = package.replace("data/", "", 1).replace(".pck", "").replace(".webp", "") + "__" + ("file" if key == "*" else key.rsplit(".", 1)[0])
        return re.sub(r"[^a-z0-9_]+", "_", name.lower())

    def full(self, package, key, original: bytes, image: Image.Image):
        name = self.stem(package, key) + ".webp"
        (self.out / name).write_bytes(swimages.encode_webp(image))
        self.entries.setdefault(package, {})[key] = {"kind": "full", "file": name, "base": swimages.sha1(original)}

    def delta(self, package, key, original: bytes, final: Image.Image):
        overlay, mask, frac = swimages.make_delta(swimages.decode(original), final)
        stem = self.stem(package, key)
        overlay.save(self.out / f"{stem}.png")
        mask.save(self.out / f"{stem}.mask.png")
        self.entries.setdefault(package, {})[key] = {"kind": "delta", "overlay": f"{stem}.png", "mask": f"{stem}.mask.png",
                                                     "base": swimages.sha1(original)}
        return frac

    def layer(self, package, key, original: bytes, size, ops, bleed, encode="exact"):
        done = []
        for op in ops:
            if op["op"] == "layer":
                name = self.stem(package, key) + "__" + op.pop("name") + ".png"
                op.pop("image").save(self.out / name)
                done.append({"op": "layer", "file": name, "at": op["at"]})
            else:
                done.append(op)
        spec = {"kind": "layer", "size": list(size), "ops": done, "base": swimages.sha1(original)}
        if bleed:
            spec["bleed"] = list(bleed)
        if encode != "exact":
            spec["encode"] = encode
        self.entries.setdefault(package, {})[key] = spec

    def finish(self, assets=None):
        manifest = {"format": 1, "containers": {"android": self.entries}}
        (self.out / swimages.MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        if assets is not None:
            self.verify(manifest, assets)
        return manifest

    def verify(self, manifest, assets):
        """Compose every entry the way the build will and compare it, pixel by pixel, with the picture that was drawn."""
        pack = SimpleNamespace(path=self.out.parent.parent)
        got, _ = aimages.pack_images(pack, assets)
        for (package, key), want in self.expect.items():
            have = swimages.decode(got[package][key])
            a, b = want.convert("RGBA"), have
            pa, pb = a.load(), b.load()
            bad = sum(1 for y in range(a.height) for x in range(a.width)
                      if pa[x, y] != pb[x, y] and (pa[x, y][3] or pb[x, y][3]))
            if a.size != b.size or bad:
                sys.exit(f"{package}/{key}: the pack composes to another picture than the one drawn ({bad} pixels differ)")


def render(lang: str, assets: AndroidAssets, out: Path) -> dict:
    texts = {**COMMON, **TEXTS[lang]}
    w = Writer(out)

    def entries(package):
        return aimages.entries_by_base(assets.read(package))

    # options screen
    package = "data/System/config.pck"
    e = entries(package)
    a = swimages.decode(e["txt_view_width.webp"])
    w.full(package, "txt_view_width.webp", e["txt_view_width.webp"],
           gen_label(a, texts["wide"], "avenir_cond", size_k=0.78, fill=(240, 240, 240), shadow=(2, 2, 2, 0.6)))
    a = swimages.decode(e["txt_view_width2.webp"])
    w.full(package, "txt_view_width2.webp", e["txt_view_width2.webp"],
           gen_label(a, texts["wide_help"], "tahoma", size_k=0.72, fill=median_color(a, 120)))

    # focus label and the mode label
    package = "data/System/systemTexture.pck"
    e = entries(package)
    w.full(package, "important.webp", e["important.webp"],
           gen_label(swimages.decode(e["important.webp"]), texts["focus"], "impact", size_k=0.82, fill=(255, 255, 255), outline=(0, 0, 0), ow=6))
    original = swimages.decode(e["trigger_mode.webp"])
    cut, txt = trigger_layer(original, texts["look"])
    w.layer(package, "trigger_mode.webp", e["trigger_mode.webp"], original.size,
            [{"op": "copy", "from": None, "box": [0, 0, original.width, cut], "to": [0, 0]},
             {"op": "layer", "name": "look", "image": txt, "at": [0, cut]}], (255, 255, 255))

    # an enemy skill name that exists only in Android's picture (the others, in English, use DIN condensed with an outline and a shadow)
    package = "data/skillname/eskillName00.webp"
    blob = assets.read(package)
    a = swimages.decode(blob)
    layer = with_shadow(ink_text_layer(texts["skill"], "din_cond", cap_size("din_cond", 118), (255, 255, 255), 5, (0, 0, 0)), (3, 0.6, 3, 4), 4)
    bb = ink(a)
    w.entries.setdefault(package, {})
    w.full(package, "*", blob, place(a.size, layer, "left", left=max(0, bb[0] - 4), vcenter=(bb[1] + bb[3]) / 2))

    # the cloud-backup screen. Nothing of the Japanese is stored: the bars are copied from the user's own picture, and the label that was on the
    # arrows is erased from it when the app is built
    package = "data/Backup/backup.pck"
    e = entries(package)
    for key, label in texts["backup_bars"].items():
        orig = swimages.decode(e[key])
        final, bars, layer, pos = gen_backup_bars(orig, label)
        ops = [{"op": "copy", "from": None, "box": [r[0], 0, r[1], orig.height], "to": [r[0], 0]} for r in bars]
        ops.append({"op": "layer", "name": "text", "image": layer, "at": list(pos)})
        w.layer(package, key, e[key], orig.size, ops, None, encode="plain")
        w.expect[(package, key)] = final
    for key, (lines, scale, dy) in texts["backup_arrows"].items():
        orig = swimages.decode(e[key])
        final, layer, pos = gen_arrow(orig, lines, scale=scale, dy=dy)
        ops = [{"op": "copy", "from": None, "box": [0, 0, orig.width, orig.height], "to": [0, 0]}, {"op": "erase_enclosed"},
               {"op": "layer", "name": "text", "image": layer, "at": list(pos)}]
        w.layer(package, key, e[key], orig.size, ops, None, encode="plain")
        w.expect[(package, key)] = final
    for key, label in texts["backup_labels"].items():
        a = swimages.decode(e[key])
        if key == "backup_day.webp":
            im = gen_label(a, label, "rounded", size_k=0.78, fill=(255, 255, 255), outline=(20, 20, 20), ow=3)
        else:
            im = gen_label(a, label, "rounded", size_k=0.74)
        w.full(package, key, e[key], im)
    key = "backup_ko.webp"                                              # the counter unit of the Japanese: no unit is written
    w.full(package, key, e[key], Image.new("RGBA", swimages.decode(e[key]).size, (0, 0, 0, 0)))

    # voice-language buttons: our label with a glow + the loudspeaker copied from the original
    package = "data/System/systemTexture3.pck"
    e = entries(package)
    icon = voice_icon_box(swimages.decode(e["text_jp.webp"]))
    for name, label in texts["voice"].items():
        key = name.lower()
        orig = swimages.decode(e[key])
        layer, x, icon_x = voice_layer(label, icon[2] - icon[0], orig.width)
        w.layer(package, key, e[key], orig.size,
                [{"op": "layer", "name": "text", "image": layer, "at": [x, 0]},
                 {"op": "copy", "from": "text_jp.webp", "box": list(icon), "to": [icon_x, 0]}], (205, 255, 255))
    return w.finish(assets)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", required=True, choices=sorted(TEXTS))
    ap.add_argument("--apk-dir", required=True, type=Path)
    ap.add_argument("--work", type=Path, default=ROOT / "work" / "android")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or ROOT / "langs" / a.lang / "android" / "images"
    with AndroidAssets(a.apk_dir, a.work) as assets:
        manifest = render(a.lang, assets, out)
    n = sum(len(v) for v in manifest["containers"]["android"].values())
    print(f"{n} pictures in {sum(len(v) for v in manifest['containers']['android'].values())} entries -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
