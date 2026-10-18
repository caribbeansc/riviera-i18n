"""The touch-mode sprites of the Android app (MOVE / QUEST) drawn again as MOVE / LOOK, with the method of the originals.

The English script calls the exploration mode "Look Mode" and its button LOOK, but the pictures only Android has said QUEST (and the
text of the game said "Look Mode": inconsistent). The Switch picture ``new\\tap_to_LOOK.webp`` cannot be used as it is (its canvas is
another one, and Android draws these sprites at the size of the original), but its four letters (L, O, O, K, in the same font as MOVE and
QUEST) can: their white masks are taken from the user's own copy and the process of the originals is repeated.

Every sprite is the word in a font of rectangular letters with three layers around the white fill:
fill · black line of about 4 px · colour ring of about 4 px (blue for MOVE, orange for QUEST/LOOK).

* **big** ones (443x166 / 416x154, the mode indicator of the corner): white fill (253), halo = gaussian blur of the body (sigma about
  17 px, gain 1.5, alpha cap 248) in black; the holes of the letters (the "O") are black from the same blur;
* **_s** ones (464x105 / 412x101, the one that appears in the middle of the screen when the mode changes): glyphs about 1.27-1.31x
  larger, **light grey (228)** fill, no halo and transparent holes.

Calibrated and validated by regenerating QUEST, MOVE, QUEST_s and MOVE_s from their own masks (alpha error 3-7/255, colour 6-8/255).
Nothing here is stored: the letters and colours are measured from the user's pictures. The Euclidean distance transform is plain Python
(no numpy); Pillow only blurs, scales and saves.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

from PIL import Image, ImageChops, ImageFilter

INF = 1e20

IS_BLACK = lambda c: max(c) < 80                                  # noqa: E731
IS_ORANGE = lambda c: c[0] > 180 and c[2] < 120                   # noqa: E731
IS_BLUE = lambda c: c[2] > 170 and c[0] < 130                     # noqa: E731
IS_FILL = lambda c: min(c) >= 200                                 # noqa: E731


def _edt1(f, n):
    d = [0.0] * n
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    z[0], z[1] = -INF, INF
    for q in range(1, n):
        while True:
            p = v[k]
            s = ((f[q] + q * q) - (f[p] + p * p)) / (2.0 * q - 2.0 * p)
            if s <= z[k]:
                k -= 1
            else:
                break
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = INF
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) ** 2 + f[v[k]]
    return d


def edt(mask: Sequence[bool], w: int, h: int) -> list[float]:
    """Euclidean distance from every pixel to the nearest true pixel of ``mask`` (a flat list of ``w * h`` booleans)."""
    g = [[0.0 if mask[y * w + x] else INF for x in range(w)] for y in range(h)]
    cols = [_edt1([g[y][x] for y in range(h)], h) for x in range(w)]
    out = [0.0] * (w * h)
    for y in range(h):
        row = _edt1([cols[x][y] for x in range(w)], w)
        for x in range(w):
            out[y * w + x] = row[x] ** 0.5 if row[x] < INF / 2 else 1e9
    return out


def clamp(v, a=0.0, b=1.0):
    return a if v < a else (b if v > b else v)


def glyph_masks(im: Image.Image, min_area: int = 200):
    """White components (the fill of the letters) of a sprite: ``[(box, 'L' image 0/255)]`` sorted by x. A letter with a loose bar (the
    "E" of QUEST) gives two components: the ones that overlap in x are joined."""
    w, h = im.size
    px = im.load()
    m = [px[x, y][3] >= 250 and min(px[x, y][:3]) >= 200 for y in range(h) for x in range(w)]
    lab = [0] * (w * h)
    comps = []
    for i in range(w * h):
        if m[i] and not lab[i]:
            n = len(comps) + 1
            st = [i]
            lab[i] = n
            pts = []
            while st:
                j = st.pop()
                pts.append(j)
                x, y = j % w, j // w
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and 0 <= yy < h and m[yy * w + xx] and not lab[yy * w + xx]:
                        lab[yy * w + xx] = n
                        st.append(yy * w + xx)
            if len(pts) >= min_area:
                xs = [p % w for p in pts]
                ys = [p // w for p in pts]
                comps.append([min(xs), min(ys), max(xs), max(ys), pts])
    comps.sort()
    merged = []
    for c in comps:
        if merged and c[0] <= merged[-1][2] and c[1] >= merged[-1][1] and c[3] <= merged[-1][3]:       # inside the previous box
            merged[-1][4] += c[4]
        else:
            merged.append(c)
    out = []
    for x0, y0, x1, y1, pts in merged:
        g = Image.new("L", (x1 - x0 + 1, y1 - y0 + 1), 0)
        pg = g.load()
        for p in pts:
            pg[p % w - x0, p // w - y0] = 255
        out.append(((x0, y0, x1, y1), g))
    return out


def soft_mask(im: Image.Image) -> list[float]:
    """White coverage 0..1 (flat list) of an original sprite, with the antialiasing of the white/black border."""
    w, h = im.size
    px = im.load()
    hard = [px[x, y][3] >= 250 and min(px[x, y][:3]) >= 200 for y in range(h) for x in range(w)]
    d = edt(hard, w, h)
    soft = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if hard[i]:
                soft[i] = 1.0
            elif d[i] < 2.0 and px[x, y][3] >= 250:
                soft[i] = clamp((min(px[x, y][:3]) - 12) / 240.0)
    return soft


def soft_glyphs(im: Image.Image, margin: int = 1):
    """The letters of a sprite with their antialiasing: ``[('L' image 0..255 with `margin` px around, hard box)]`` sorted by x."""
    w, h = im.size
    soft = soft_mask(im)
    out = []
    for (x0, y0, x1, y1), _ in glyph_masks(im):
        g = Image.new("L", (x1 - x0 + 1 + 2 * margin, y1 - y0 + 1 + 2 * margin), 0)
        pg = g.load()
        for y in range(g.height):
            for x in range(g.width):
                xx, yy = x0 - margin + x, y0 - margin + y
                if 0 <= xx < w and 0 <= yy < h:
                    pg[x, y] = round(soft[yy * w + xx] * 255)
        out.append((g, (x0, y0, x1, y1)))
    return out


def compose_word(glyphs, canvas, scale, pitch, x0, y0, margin: int = 1) -> list[float]:
    """Put the letters (images from :func:`soft_glyphs`, at native scale) on a canvas ``(w, h)``: each one scaled by ``scale=(sx, sy)``,
    ``pitch`` px apart (on the canvas), the first one with the top left corner of its hard box at ``(x0, y0)``. Returns the white
    coverage (flat list 0..1)."""
    w, h = canvas
    sx, sy = scale
    m = Image.new("L", (w, h), 0)
    for k, g in enumerate(glyphs):
        gs = g.resize((round(g.width * sx), round(g.height * sy)), Image.BICUBIC) if (sx, sy) != (1.0, 1.0) else g
        layer = Image.new("L", (w, h), 0)
        layer.paste(gs, (round(x0 + k * pitch - margin * sx), round(y0 - margin * sy)))
        m = ImageChops.lighter(m, layer)
    return [v / 255.0 for v in m.tobytes()]


def render(soft, w, h, ring, black, fill=(255, 255, 255), b=4.0, r=4.5, halo=None, halo_color=(2, 1, 2)) -> Image.Image:
    """The layers from the white coverage ``soft``: ring (from ``b + r`` px of the border of the white), black line (``b`` px) and fill.
    ``halo=(sigma, gain)`` adds the halo of the big sprites (gaussian blur of the body; maximum alpha 0.973 = 248/255)."""
    hard = [v >= 0.5 for v in soft]
    d = edt(hard, w, h)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    po = out.load()
    A = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            s = d[i] - 0.5 if d[i] > 0 else -0.5
            a_r = clamp((b + r) - s + 0.5)
            a_b = clamp(b - s + 0.5)
            a_w = soft[i]
            a2 = a_b + a_r * (1 - a_b)
            c2 = [(black[k] * a_b + ring[k] * a_r * (1 - a_b)) / a2 if a2 > 0 else 0 for k in range(3)]
            a3 = a_w + a2 * (1 - a_w)
            c3 = [(fill[k] * a_w + c2[k] * a2 * (1 - a_w)) / a3 if a3 > 0 else 0 for k in range(3)]
            A[i] = a3
            po[x, y] = (round(c3[0]), round(c3[1]), round(c3[2]), round(a3 * 255))
    if halo:
        sig, gain = halo
        m = Image.new("L", (w, h))
        m.putdata([round(min(1.0, a) * 255) for a in A])
        pb = m.filter(ImageFilter.GaussianBlur(sig)).load()
        for y in range(h):
            for x in range(w):
                a = A[y * w + x]
                if a < 1.0:
                    ha = clamp(gain * pb[x, y] / 255.0, 0.0, 0.973)
                    aa = po[x, y][3] / 255.0
                    at = aa + ha * (1 - aa)
                    if at > 0:
                        po[x, y] = tuple([round((po[x, y][k] * aa + halo_color[k] * ha * (1 - aa)) / at) for k in range(3)] + [round(at * 255)])
    return out


def bleed(im: Image.Image, color) -> Image.Image:
    """RGB of the fully transparent pixels = ``color`` (the ring's): the originals keep the ring colour under the transparency, and a
    scaled or filtered sprite then blends its edge with that colour instead of black."""
    im = im.convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if px[x, y][3] == 0:
                px[x, y] = (color[0], color[1], color[2], 0)
    return im


def mean_color(im: Image.Image, test) -> tuple[int, int, int]:
    px = im.load()
    pts = [px[x, y][:3] for y in range(im.height) for x in range(im.width) if px[x, y][3] >= 250 and test(px[x, y][:3])]
    return tuple(round(sum(p[k] for p in pts) / len(pts)) for k in range(3))


def encode_webp_exact(im: Image.Image) -> bytes:
    """Lossless WebP that keeps the colour of the transparent pixels (``exact``), which is what the sprites above need."""
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, "WEBP", lossless=True, quality=100, method=6, exact=True)
    return buf.getvalue()


def look_sprites(look_letters: Image.Image, big_original: Image.Image, small_original: Image.Image) -> tuple[Image.Image, Image.Image]:
    """``(big, small)``: the QUEST sprites of the corner indicator (``new\\tap_to_quest.webp``) and of the centre notice
    (``tap_to_quest_s.webp``) redrawn as LOOK. ``look_letters`` is the Switch picture of the word LOOK (four letters), the other two
    are the user's Android originals, from which the canvas size, the colours and the vertical position are taken."""
    letters = [g for g, _ in soft_glyphs(look_letters.convert("RGBA"))]
    if len(letters) != 4:
        raise ValueError(f"expected 4 letters in the picture of LOOK, found {len(letters)}")
    q_big, q_s = big_original.convert("RGBA"), small_original.convert("RGBA")

    # big: canvas, colours and vertical position of QUEST; the word is centred where QUEST was
    ring = mean_color(q_big, IS_ORANGE)
    black = mean_color(q_big, IS_BLACK)
    cw, ch = q_big.size
    pitch = 71.75
    x0 = round(215.5 - (3 * pitch + 59 + 16) / 2 + 8)
    soft = compose_word(letters, (cw, ch), (1.0, 1.0), pitch, x0, 47)
    big = render(soft, cw, ch, ring, black, (254, 254, 254), 4.0, 4.0, (17, 1.5))

    # _s: glyphs of the size of those of QUEST_s (75x89, pitch 93), light grey fill, no halo
    ring_s = mean_color(q_s, IS_ORANGE)
    black_s = mean_color(q_s, IS_BLACK)
    fill_s = mean_color(q_s, IS_FILL)
    cw, ch = q_s.size
    pitch_s = 93.0
    x0s = round((cw - (3 * pitch_s + 75 + 16)) / 2 + 8)
    soft = compose_word(letters, (cw, ch), (75 / 59.0, 89 / 68.0), pitch_s, x0s, 8)
    small = bleed(render(soft, cw, ch, ring_s, black_s, fill_s, 4.0, 4.0, None), ring_s)
    return big, small
