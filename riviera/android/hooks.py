"""Proportional text for the Android engine: install the precompiled hooks into ``libapp.so``.

The Android text engine advances one fixed cell per character, as it does for Japanese. English (and every translation in Latin
script) needs the per-cell widths that the PC build and the Switch use. ``tools/android/hooks.c`` reproduces that on top of the
Android functions; ``tools/android/build_hooks.py`` compiles it once, and its output is what this module installs::

    riviera/android/data/hooks.bin    the blob: code only, linked at a fixed address
    riviera/android/data/hooks.json   where everything is inside it, and the sites of the game it hooks

**The blob holds no game data.** The engine's metrics tables and character string are zero-filled holes, and each hook's displaced
instruction is a ``nop`` slot. :func:`install` fills them from the user's own files (the Switch executable, and the library itself).
The library is pinned by its SHA-256 and every site is also checked by a fingerprint of ``address + original word``, so a different
version of the app is refused before anything is written.

The blob lives at the start of the segment the build appends to the library (see :data:`RESERVE`); the text goes after it.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path

from .. import builds
from ..nso import HEADER
from .elf import Elf
from . import AndroidError

DATA_DIR = Path(__file__).with_name("data")
RESERVE = 0x4000                  # bytes the appended segment leaves for the blob at its start (the blob is about 12 KB)


class HooksError(AndroidError):
    """The hooks cannot be installed in this library."""


def site_fingerprint(addr: int, word: bytes) -> str:
    """Short fingerprint of the instruction word at ``addr``: it identifies the expected original without storing it."""
    return hashlib.sha1(b"%x:" % addr + bytes(word)).hexdigest()[:12]


def b_insn(src: int, dst: int) -> bytes:
    """``b dst`` encoded for the address ``src``."""
    delta = dst - src
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise HooksError(f"cannot branch from 0x{src:x} to 0x{dst:x}")
    return struct.pack("<I", 0x14000000 | ((delta // 4) & 0x3FFFFFF))


def adrp_add(src: int, target: int, rd: int, rn: int) -> bytes:
    """``adrp xRd, target; add xRd, xRn, #lo12`` for the pair placed at ``src`` and ``src + 4``."""
    pages = (target >> 12) - (src >> 12)
    if not -(1 << 20) <= pages < (1 << 20):
        raise HooksError(f"0x{target:x} is out of the range of adrp at 0x{src:x}")
    adrp = 0x90000000 | ((pages & 3) << 29) | (((pages >> 2) & 0x7FFFF) << 5) | rd
    add = 0x91000000 | ((target & 0xFFF) << 10) | (rn << 5) | rd
    return struct.pack("<II", adrp, add)


@dataclass
class Hooks:
    blob: bytes
    meta: dict

    @property
    def base(self) -> int:
        """Address the blob was linked at: the start of the appended segment."""
        return self.meta["base"]

    @property
    def library_sha256(self) -> str:
        return self.meta["library_sha256"]


def load(directory=None) -> Hooks:
    """The shipped blob and its description (or those of ``directory``)."""
    d = Path(directory) if directory else DATA_DIR
    try:
        meta = json.loads((d / "hooks.json").read_text(encoding="utf-8"))
        blob = (d / "hooks.bin").read_bytes()
    except OSError as e:
        raise HooksError(f"the precompiled hooks are missing ({e})") from None
    if len(blob) != meta["size"]:
        raise HooksError("hooks.bin does not match hooks.json")
    return Hooks(blob, meta)


def engine_tables(nso, hooks: Hooks, font_writes: dict | None = None, build=None) -> tuple[dict[str, bytes], bytes]:
    """The engine's own data the hooks need, copied from the user's executable: ``({"M1": ..., "M2": ..., "M3": ...}, character string)``.

    ``font_writes`` (``offset in the NSO image -> bytes``, from :mod:`riviera.font`) are applied first, so the metrics of the glyphs the
    font patch adds and the character string with ``¿ ¡`` are the ones the translated game uses."""
    build = build or builds.for_nso(nso)
    mem = bytearray(nso.mem)
    for off, data in (font_writes or {}).items():
        mem[off - HEADER:off - HEADER + len(data)] = data
    tables = {}
    for n, (slot, lo, hi) in enumerate(build.metric_tables, 1):
        want = hooks.meta["tables"][f"M{n}"]
        if (lo, hi - lo + 1) != (want["first"], want["count"]):
            raise HooksError(f"metrics table {n} of this executable ({lo}-{hi}) is not the one the hooks were built for")
        start = nso.relocs[slot]
        tables[f"M{n}"] = bytes(mem[start:start + 6 * (hi - lo + 1)])
    charset = bytes(mem[build.charset_addr:mem.index(b"\0", build.charset_addr)])
    return tables, charset


def install(elf: Elf, segment_offset: int, segment_vaddr: int, *, tables: dict[str, bytes],
            charset: bytes | None = None, hooks: Hooks | None = None) -> dict:
    """Write the blob at the start of the appended segment and hook the game's code.

    ``tables`` are the metrics (see :func:`engine_tables`). ``charset``, if given, is the extended character string: it is copied into
    the blob and ``FNT_init`` is pointed at it (only the translations with accents or ``¿ ¡`` need it). Nothing is written unless every
    site of the game holds the instruction the hooks expect. Returns a summary."""
    h = hooks or load()
    m = h.meta
    if segment_vaddr != m["base"]:
        raise HooksError(f"the appended segment starts at 0x{segment_vaddr:x} but the hooks were linked for 0x{m['base']:x}")
    if m["size"] > RESERVE:
        raise HooksError("the hooks do not fit the space reserved for them")

    bad = []

    def check(addr: int, fingerprint: str, size: int = 4) -> None:
        if site_fingerprint(addr, elf.read(addr, size)) != fingerprint:
            bad.append(addr)

    for hk in m["hooks"]:
        check(hk["addr"], hk["orig"])
        if hk["resume"]:
            check(hk["resume"], hk["resume_orig"])
    for r in m["replace"]:
        check(r["addr"], r["orig"])
    for p in m["patches"]:
        check(p["addr"], p["orig"])
    init = m["init_charset"]
    if charset is not None:
        check(init["addr"], init["orig"], 8)
    if bad:
        raise HooksError("this is not the version of the library the hooks were made for (unexpected code at "
                         + ", ".join(f"0x{a:x}" for a in sorted(set(bad))[:6]) + ")")

    blob = bytearray(h.blob)
    for name, spec in m["tables"].items():
        if name == "charset":
            continue
        data = tables[name]
        if len(data) != spec["size"]:
            raise HooksError(f"table {name} has {len(data)} bytes, expected {spec['size']}")
        blob[spec["off"]:spec["off"] + spec["size"]] = data
    spec = m["tables"]["charset"]
    if charset is not None:
        if len(charset) + 1 > spec["size"]:
            raise HooksError("the character string does not fit the space reserved for it")
        blob[spec["off"]:spec["off"] + len(charset)] = charset
    for hk in m["hooks"]:
        if hk["slot"] is not None:                                   # the instruction the hook displaced, from the user's own library
            blob[hk["slot"]:hk["slot"] + 4] = elf.read(hk["addr"], 4)

    elf.data[segment_offset:segment_offset + len(blob)] = blob
    for hk in m["hooks"]:
        elf.write(hk["addr"], b_insn(hk["addr"], m["base"] + hk["cave"]))
    for r in m["replace"]:
        elf.write(r["addr"], b_insn(r["addr"], m["base"] + r["to"]))
    for p in m["patches"]:
        elf.write(p["addr"], bytes.fromhex(p["new"]))
    if charset is not None:
        elf.write(init["addr"], adrp_add(init["addr"], m["base"] + spec["off"], init["reg"], init["reg"]))
    return {"hooks": len(m["hooks"]), "replaced": len(m["replace"]), "patches": len(m["patches"]), "charset": charset is not None}
