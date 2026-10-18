#!/usr/bin/env python3
"""A contact sheet of the original and the translated pictures of a spec, to check by eye what ``render_images.py`` drew.

Usage::

    python tools/compare_images.py --spec langs/es/images/specs/narrative.json --out work/switch/compare.png [FILTER ...]

Every row shows the name of the picture, its new text and the sizes, then the original picture and, below it, the new one, on a
blue background so that the transparency shows. The sheet is as tall as the pictures it holds: name a few of them with FILTER
(substrings of the picture name; none means every picture of the spec) to keep it short.

``--originals``  the packages of the game, as ``python rpl.py unpack`` writes them (default ``work/switch/data_en``)
``--rendered``   the packages that ``render_images.py`` wrote (default ``work/switch/rendered``)
``--spec``       the render spec(s) to show; repeat the option to merge several
``--out``        the PNG to write (default ``work/switch/compare.png``)
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageDraw  # noqa: E402

from render_images import RenderError, merge_specs  # noqa: E402
from riviera.config import user_dir  # noqa: E402
from riviera.pck import entry_name, read_pck  # noqa: E402

MAX_WIDTH = 1600


def entries(path: Path) -> dict[str, bytes]:
    """``{picture name: bytes}`` of a package."""
    _, ents = read_pck(path.read_bytes())
    out: dict[str, bytes] = {}
    for ent in ents:
        out.setdefault(entry_name(ent[0]), ent[1])
    return out


def decode(blob: bytes) -> Image.Image:
    return Image.open(io.BytesIO(blob)).convert("RGBA")


def collect(originals: Path, rendered: Path, spec: dict, filters: list[str]) -> list[tuple]:
    """``(name, text, original picture, new picture)`` for every picture of the spec that passes the filters."""
    rows = []
    for package, items in spec.items():
        old_path, new_path = originals / "data" / package, rendered / "data" / package
        for path in (old_path, new_path):
            if not path.is_file():
                raise RenderError(f"{path} does not exist (draw the pictures with tools/render_images.py first, "
                                  "and point --originals and --rendered at the right folders)")
        if package.lower().endswith(".webp"):            # a loose picture: the spec is the entry itself
            pictures = {package: (items, old_path.read_bytes(), new_path.read_bytes())}
        else:
            old, new = entries(old_path), entries(new_path)
            pictures = {}
            for name, entry in items.items():
                for where, found in (("the original", old), ("the rendered package", new)):
                    if name not in found:
                        raise RenderError(f"{package} has no picture called {name} in {where}")
                pictures[name] = (entry, old[name], new[name])
        for name, (entry, old_blob, new_blob) in pictures.items():
            if filters and not any(f in name for f in filters):
                continue
            rows.append((name, entry.get("texto", ""), decode(old_blob), decode(new_blob)))
    return rows


def make_sheet(rows: list[tuple]) -> Image.Image:
    W = min(MAX_WIDTH, max(max(a.size[0], b.size[0]) for _, _, a, b in rows) + 20)
    H = sum(a.size[1] + b.size[1] + 30 for _, _, a, b in rows)
    sheet = Image.new("RGBA", (W, H), (60, 80, 130, 255))
    d = ImageDraw.Draw(sheet)
    y = 0
    for name, text, a, b in rows:
        d.text((2, y), f"{name}  ->  {text}  [{a.size[0]}x{a.size[1]} -> {b.size[0]}x{b.size[1]}]", fill=(255, 255, 0, 255))
        y += 13
        sheet.alpha_composite(a, (0, y))
        y += a.size[1] + 2
        sheet.alpha_composite(b, (0, y))
        y += b.size[1] + 15
    return sheet.convert("RGB")


def main(argv=None) -> int:
    work = user_dir() / "work" / "switch"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("filters", nargs="*", metavar="FILTER", help="show only the pictures whose name contains one of these")
    ap.add_argument("--originals", type=Path, default=work / "data_en", metavar="DIR",
                    help="the unpacked data_en.bin (default: work/switch/data_en)")
    ap.add_argument("--rendered", type=Path, default=work / "rendered", metavar="DIR",
                    help="the packages that render_images.py wrote (default: work/switch/rendered)")
    ap.add_argument("--spec", type=Path, action="append", required=True, metavar="FILE",
                    help="a render spec; repeat the option to merge several")
    ap.add_argument("--out", type=Path, default=work / "compare.png", metavar="PNG",
                    help="the sheet to write (default: work/switch/compare.png)")
    args = ap.parse_args(argv)
    try:
        rows = collect(args.originals, args.rendered, merge_specs(args.spec), args.filters)
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("nothing to compare", file=sys.stderr)
        return 1
    sheet = make_sheet(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(f"{len(rows)} pictures -> {args.out} {sheet.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
