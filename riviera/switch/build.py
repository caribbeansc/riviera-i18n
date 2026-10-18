"""Build the Switch mod for one language.

The result is a LayeredFS mod that works on emulators (Ryujinx and forks, yuzu and forks, Eden) and, laid out as an
Atmosphère package, on a console::

    <out>/exefs/<build id>.ips        the translated script, the glyph metrics and the font string patched into ``main``
    <out>/exefs/<first 16 bytes>.ips  the same patch, named the way Ryujinx and Atmosphère look for it
    <out>/romfs/data.bin              the font atlas, extended with the accented letters
    <out>/romfs/data_en.bin           the translated pictures
    <out>/report.json                 rows that overflow their box, characters with no glyph, verification results

The mod takes the place of the game's English: run the game with its language set to English.
"""

from __future__ import annotations

import collections
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .. import builds, compose, font, images, ips, sge
from ..config import Project
from ..nso import HEADER, Nso, read_rows
from ..packs import LangPack


class BuildError(Exception):
    """The mod cannot be built (unknown build, missing pictures, verification failed)."""


@dataclass
class BuildReport:
    out_dir: Path
    summary: dict = field(default_factory=dict)
    overflow: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        s = self.summary
        return not (s.get("no_room") or s.get("verification_failures"))


def verify(nso: Nso, ips_bytes: bytes, want: dict, placed: dict, font_writes: dict) -> int:
    """Apply the patch and read every string back; returns the number of mismatches."""
    img = ips.apply_ips(ips_bytes, nso.image)
    check = Nso.from_image(img)
    bad = 0
    for slot, addr in placed.items():
        addend, = struct.unpack_from("<q", img, HEADER + nso.rela_entry[slot] + 16)
        if addend != addr or check.cstr(addr) != want[slot][1]:
            bad += 1
    for off, data in font_writes.items():
        if img[off:off + len(data)] != data:
            bad += 1
    return bad


def build(project: Project, pack: LangPack, out_dir=None, *, soft: float | None = None, with_romfs: bool = True,
          say=print) -> BuildReport:
    """Build the mod of ``pack`` from the dump configured in ``project``."""
    exefs, romfs = project.require_switch()
    out_dir = Path(out_dir) if out_dir else project.switch_build(pack.code)
    soft = pack.platform("switch").get("soft", 1.0) if soft is None else soft

    say("Reading the executable")
    nso = Nso(exefs / "main")
    try:
        build_info = builds.for_nso(nso)
    except builds.UnknownBuild as e:
        raise BuildError(str(e)) from None
    rows = read_rows(nso)
    db = pack.text()
    if not db:
        raise BuildError(f"the {pack.code} pack has no script (langs/{pack.code}/text.jsonl)")

    say("Drawing the accented letters")
    with sge.Archive(romfs / "data.bin") as arc:
        atlas = font.make_atlas(nso, arc.read_path(font.ATLAS_PCK), build_info)
    M, charset = font.font_metrics(nso, atlas.writes, build_info)
    charset_new = charset
    for new, old in font.REPLACE.items():           # the game has no Þ or Ð in those cells any more
        charset_new = charset_new.replace(old, new)

    say("Composing the script")
    want, overflow, skipped, chars, caps = compose.build_text(nso, rows, db, M, charset_new, soft)
    miss = font.missing_glyphs(chars, charset_new)

    pool = compose.free_regions(nso, rows)
    writes, placed, relocate, unplaced, left = ips.place(nso, want, pool)
    for off, data in atlas.writes.items():
        writes.put(off, data)
    ips_bytes = ips.to_ips(writes, nso.image)
    bad = verify(nso, ips_bytes, want, placed, atlas.writes)

    out_dir = Path(out_dir)
    (out_dir / "exefs").mkdir(parents=True, exist_ok=True)
    for name in dict.fromkeys(build_info.ips_names):
        (out_dir / "exefs" / f"{name}.ips").write_bytes(ips_bytes)

    report = BuildReport(out_dir=out_dir, overflow=overflow)
    by_block = collections.Counter(o["block"] for o in overflow)
    report.summary = {
        "build_id": nso.build_id, "language": pack.code, "rows_translated": len(want),
        "in_place": len(want) - len(relocate), "relocated": len(relocate) - len(unplaced), "no_room": len(unplaced),
        "segments_mismatch": skipped, "overflow": len(overflow), "overflow_by_block": dict(sorted(by_block.items())),
        "missing_glyphs": miss, "verification_failures": bad, "free_bytes": sum(e - s for s, e in left),
        "ips_bytes": len(ips_bytes), "soft": soft,
        "caps_by_block": {"%s%s" % (b, "/" + g if g else ""): list(v) for (b, g), v in sorted(caps.items())},
    }

    if with_romfs:
        say("Packing the pictures")
        (out_dir / "romfs").mkdir(parents=True, exist_ok=True)
        replacements, warn = images.translated_packages(pack.path, romfs / "data_en.bin")
        report.warnings += warn
        sge.pack(romfs / "data.bin", {font.ATLAS_PCK: atlas.pck}, out_dir / "romfs" / "data.bin")
        sge.pack(romfs / "data_en.bin", replacements, out_dir / "romfs" / "data_en.bin")
        report.summary["pictures_replaced"] = sum(len(e) for e in images.packages(images.load_manifest(pack.path), "data_en.bin").values())

    (out_dir / "report.json").write_text(
        json.dumps({"summary": report.summary, "overflow": overflow, "warnings": report.warnings}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return report
