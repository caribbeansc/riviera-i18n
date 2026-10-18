#!/usr/bin/env python3
"""Turn rendered artwork into the files a language pack ships (full pictures and deltas).

This is a contributor tool, not part of the build: the pictures of a language are drawn once (with ``tools/render_images.py``,
which needs fonts you may not have), and this script stores the result in ``langs/<code>/images/`` in the two forms the
builder understands (see riviera/images.py and docs/specs/SPEC-003-image-delta.md).

    python tools/images_pack.py --code es --container data_en.bin \\
        --originals work/switch/data_en --rendered work/switch/rendered \\
        --spec langs/es/images/specs/narrative.json --spec langs/es/images/specs/explanations.json

* ``--originals``: the packages as they come out of the game, laid out by ``python rpl.py unpack`` (``data/event/demo1.pck`` ...).
* ``--rendered``: the same layout, with the packages that contain translated pictures.
* ``--spec``: the render specs; only the ``estilo`` of each entry is read, to decide how it is stored. A picture rendered by
  an ``--delta-styles`` style (default: ``patch`` and ``year``) that keeps parts of the original (a title, a logo) is stored as a delta
  when it has the original's size, with a **rectangular mask** (the bounding box of the changes: the exact mask of a label that was
  erased and redrawn would be a silhouette of the original label). Everything else is text drawn on an empty canvas and is stored as it is.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from riviera import images, pck  # noqa: E402


def styles_of(specs: list[str]) -> dict:
    out = {}
    for sp in specs:
        for package, entries in json.loads(Path(sp).read_text(encoding="utf-8")).items():
            for name, item in entries.items():
                out[(package, name)] = item.get("estilo", "")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--code", required=True)
    ap.add_argument("--container", default="data_en.bin")
    ap.add_argument("--originals", required=True)
    ap.add_argument("--rendered", required=True)
    ap.add_argument("--spec", action="append", default=[])
    ap.add_argument("--delta-styles", default="patch,year")
    ap.add_argument("--langs", default=str(Path(__file__).resolve().parent.parent / "langs"))
    args = ap.parse_args(argv)

    delta_styles = {s for s in args.delta_styles.split(",") if s}
    styles = styles_of(args.spec)
    pack_dir = Path(args.langs) / args.code
    out_root = pack_dir / "images" / Path(args.container).stem
    shutil.rmtree(out_root, ignore_errors=True)                      # what is not rewritten below must not survive
    originals, rendered = Path(args.originals), Path(args.rendered)
    manifest = {"format": 1, "containers": {args.container: {}}}
    counts = {"full": 0, "delta": 0, "unchanged": 0}
    for new_file in sorted(rendered.rglob("*.pck")):
        package = new_file.relative_to(rendered).as_posix()                       # data/event/demo1.pck
        old_file = originals / package
        if not old_file.is_file():
            print(f"skip {package}: no original", file=sys.stderr)
            continue
        _, old = pck.read_pck(old_file.read_bytes())
        old = {pck.entry_name(e[0]): e[1] for e in old}
        _, new = pck.read_pck(new_file.read_bytes())
        spec_key = package[len("data/"):] if package.startswith("data/") else package
        entries = {}
        for raw, blob in new:
            name = pck.entry_name(raw)
            if name not in old:
                raise SystemExit(f"{package}/{name}: not in the original package")
            if blob == old[name]:
                counts["unchanged"] += 1
                continue
            folder = out_root / package
            folder.mkdir(parents=True, exist_ok=True)
            spec = {"base": images.sha1(old[name])}
            style = styles.get((spec_key, name), "")
            original_im, new_im = images.decode(old[name]), images.decode(blob)
            delta = None
            if style in delta_styles and original_im.size == new_im.size:
                delta = images.make_delta(original_im, new_im, rect=True)
            if delta:
                overlay, mask, fraction = delta
                stem = Path(name).stem
                overlay.save(folder / f"{stem}.png", optimize=True)
                mask.save(folder / f"{stem}.mask.png", optimize=True)
                rel = (folder / stem).relative_to(out_root.parent).as_posix()
                spec.update(kind="delta", overlay=rel + ".png", mask=rel + ".mask.png", changed=round(fraction, 3))
                counts["delta"] += 1
            else:
                (folder / name).write_bytes(blob)
                spec.update(kind="full", file=(folder / name).relative_to(out_root.parent).as_posix())
                counts["full"] += 1
            entries[name] = spec
        if entries:
            manifest["containers"][args.container][package] = entries
    (pack_dir / "images").mkdir(parents=True, exist_ok=True)
    (pack_dir / "images" / images.MANIFEST).write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
