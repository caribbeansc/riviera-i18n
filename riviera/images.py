"""Translated artwork without shipping the game's artwork.

Some text is baked into pictures (the intro, the chapter cards, the captions of the CG, the explanations of the options). A
language pack stores two kinds of picture, listed in ``langs/<code>/images/manifest.json``:

``full``
    A picture the translation draws entirely itself: text on an empty, transparent canvas. It replaces the game's picture
    as it is. It may have another size than the original (the engine draws every picture at its own native size).

``delta``
    A translation that edits a picture that keeps its panels, buttons or logo. Shipping the edited picture would ship the
    game's artwork, so only *the difference* is stored::

        <name>.png        RGBA overlay: the final value of every changed pixel
        <name>.mask.png   L mask: 255 where a pixel changed

    The mask is needed because a pixel can change *to* transparent (erasing text that sits on an alpha background), which
    the overlay alone cannot tell from "unchanged". The builder rebuilds the final picture as *the original from your own
    dump* + the delta (SPEC-003).

Every entry also carries ``base``: the SHA-1 of the original picture it was made against. A different one means a different
version of the game, and the build says so instead of pasting a translation over the wrong picture.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageChops

from . import pck, sge

MANIFEST = "manifest.json"


class ImageError(Exception):
    """A picture cannot be rebuilt (missing file, different base, bad delta)."""


def sha1(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()


def decode(blob: bytes) -> Image.Image:
    return Image.open(io.BytesIO(blob)).convert("RGBA")


def encode_webp(im: Image.Image) -> bytes:
    """Lossless WebP, the way the translated artwork is stored in the game's packages."""
    buf = io.BytesIO()
    im.save(buf, "WEBP", lossless=True, quality=100, method=4)
    return buf.getvalue()


def changed_mask(original: Image.Image, translated: Image.Image) -> Image.Image:
    """``L`` mask, 255 where a pixel differs. Two fully transparent pixels are equal whatever their RGB (SPEC-003/R-2)."""
    r, g, b, a = ImageChops.difference(original, translated).split()
    diff = ImageChops.lighter(ImageChops.lighter(r, g), ImageChops.lighter(b, a)).point(lambda v: 255 if v else 0)
    both_clear = ImageChops.multiply(original.getchannel("A").point(lambda v: 255 if v == 0 else 0),
                                     translated.getchannel("A").point(lambda v: 255 if v == 0 else 0))
    return ImageChops.subtract(diff, both_clear)


def make_delta(original: Image.Image, translated: Image.Image, *, rect: bool = False) -> tuple[Image.Image, Image.Image, float]:
    """``(overlay, mask, changed fraction)`` such that :func:`apply_delta` turns ``original`` into ``translated``.

    With ``rect`` the mask is the bounding rectangle of the changes instead of the exact changed pixels. The picture that is rebuilt is
    the same, but the mask no longer traces the glyphs of the text that was replaced (the exact mask of a label that was erased and
    redrawn is a silhouette of the original label), so a delta that is published should use it.
    """
    if original.size != translated.size:
        raise ImageError("a delta needs pictures of the same size")
    mask = changed_mask(original, translated)
    if rect and mask.getbbox():
        box = mask.getbbox()
        mask = Image.new("L", original.size, 0)
        mask.paste(255, box)
    overlay = Image.new("RGBA", original.size, (0, 0, 0, 0))
    overlay.paste(translated, (0, 0), mask)
    hist = mask.histogram()
    return overlay, mask, 1 - hist[0] / sum(hist)


def apply_delta(original: Image.Image, overlay: Image.Image, mask: Image.Image) -> Image.Image:
    if overlay.size != original.size or mask.size != original.size:
        overlay = overlay.resize(original.size, Image.NEAREST)           # SPEC-003/R-7: never cropped
        mask = mask.resize(original.size, Image.NEAREST)
    return Image.composite(overlay.convert("RGBA"), original.convert("RGBA"), mask.convert("L"))


def load_manifest(pack_dir) -> dict:
    f = Path(pack_dir) / "images" / MANIFEST
    if not f.is_file():
        return {"format": 1, "containers": {}}
    return json.loads(f.read_text(encoding="utf-8"))


def packages(manifest: dict, container: str) -> dict:
    """``{package path: {entry name: spec}}`` of one container (``data_en.bin``)."""
    return manifest.get("containers", {}).get(container, {})


def build_package(pack_dir, entries: dict, original: bytes, *, label: str = "") -> tuple[bytes, list[str]]:
    """The translated version of one ``.pck`` package, from its original bytes.

    ``entries`` is ``{entry name: spec}`` from the manifest. Returns ``(new package, warnings)``; the warnings list every
    picture whose original is not the one the translation was made against.
    """
    base = Path(pack_dir) / "images"
    data0, ents = pck.read_pck(original)
    index = {pck.entry_name(e[0]): e for e in ents}
    warnings = []
    for name, spec in entries.items():
        if name not in index:
            raise ImageError(f"{label}: the package has no picture called {name}")
        ent = index[name]
        if spec.get("base") and sha1(ent[1]) != spec["base"]:
            warnings.append(f"{label}{'/' if label else ''}{name}: not the picture this translation was made against")
        if spec["kind"] == "full":
            ent[1] = (base / spec["file"]).read_bytes()
        elif spec["kind"] == "delta":
            overlay = Image.open(base / spec["overlay"])
            mask = Image.open(base / spec["mask"])
            ent[1] = encode_webp(apply_delta(decode(ent[1]), overlay, mask))
        else:
            raise ImageError(f"{label}/{name}: unknown kind {spec['kind']!r}")
    return pck.write_pck(data0, ents), warnings


def translated_packages(pack_dir, container_path, container: str = "data_en.bin") -> tuple[dict[str, bytes], list[str]]:
    """Every translated package of ``container`` built from the player's own container: ``{path inside it: new bytes}``.

    ``container_path`` is the user's ``data_en.bin`` (the Switch one, or any build whose packages carry the same pictures).
    Returns the packages and the list of warnings (pictures whose original is not the one the translation was made against).
    """
    wanted = packages(load_manifest(pack_dir), container)
    out: dict[str, bytes] = {}
    warnings: list[str] = []
    with sge.Archive(container_path) as arc:
        where = {p: (name, info, value) for p, name, info, value in arc.walk()}
        for package, entries in wanted.items():
            if package not in where:
                raise ImageError(f"{container} has no {package}: is this the same version of the game?")
            out[package], warn = build_package(pack_dir, entries, arc.read(*where[package]), label=package)
            warnings += warn
    return out, warnings
