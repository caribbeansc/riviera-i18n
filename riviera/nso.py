"""Read the script out of the game's ``main`` executable (an NSO).

The whole script lives in one table of pointers (``R_AARCH64_RELATIVE`` entries in
``.rela.dyn``) to UTF-8 strings in ``.rodata``. The table is a run of blocks that
look like this::

    [4 empty strings, only in some blocks][EN n][JP n][KR n][TC n]

Rows line up across languages: ``EN[k]``, ``JP[k]``, ``KR[k]`` and ``TC[k]`` are the
same sentence. Nothing here depends on a fixed address:

* the longest run of consecutive pointers to valid UTF-8 text is the table;
* pointers *outside* the table (in ``.data``) form descriptors: four pointers with
  a constant stride are one block (start of the English rows and ``n``); the others
  point at the empty headers, and the gap between two headers gives
  ``n = (gap - 4) / 4``.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Iterator
from pathlib import Path

R_AARCH64_RELATIVE = 1027
HEADER = 0x100                          # an IPS offset includes the NSO's 0x100-byte header
TAG = re.compile(r"^V\(([^)]*)\)")


def lz4_block(src: bytes, size: int) -> bytes:
    """Decompress a raw LZ4 block (no frame header), which is what NSO segments use."""
    out = bytearray()
    i = 0
    while i < len(src):
        token = src[i]; i += 1
        n = token >> 4
        if n == 15:
            while True:
                b = src[i]; i += 1; n += b
                if b != 255:
                    break
        out += src[i:i + n]; i += n
        if i >= len(src):
            break
        off = src[i] | src[i + 1] << 8; i += 2
        n = token & 15
        if n == 15:
            while True:
                b = src[i]; i += 1; n += b
                if b != 255:
                    break
        n += 4
        if off >= n:
            out += out[-off:len(out) - off + n]
        else:                               # overlapping match: the last `off` bytes repeat
            chunk = bytes(out[-off:])
            out += (chunk * (n // off + 1))[:n]
    if len(out) != size:
        raise ValueError(f"LZ4 block decoded to {len(out)} bytes, expected {size}")
    return bytes(out)


def load_nso(path) -> tuple[bytes, str]:
    """``(decompressed image with its 0x100-byte header, build id as hex)``."""
    d = Path(path).read_bytes()
    if d[:4] != b"NSO0":
        raise ValueError(f"{path} is not an NSO")
    flags, = struct.unpack_from("<I", d, 0x0C)
    segs = [struct.unpack_from("<III", d, 0x10 + 0x10 * i) for i in range(3)]
    csizes = struct.unpack_from("<III", d, 0x60)
    parts = []
    for i, (fo, mo, size) in enumerate(segs):
        raw = d[fo:fo + (csizes[i] if flags >> i & 1 else size)]
        parts.append((mo, lz4_block(raw, size) if flags >> i & 1 else raw))
    img = bytearray(d[:0x100])
    for mo, data in parts:
        img += b"\0" * (0x100 + mo - len(img))
        img += data
    struct.pack_into("<I", img, 0x0C, flags & ~7)          # no longer compressed
    return bytes(img), d[0x40:0x60].hex().upper()


class Nso:
    """A loaded executable: its memory image, relocations and string helpers."""

    def __init__(self, path):
        self._init(*load_nso(path))

    @classmethod
    def from_image(cls, image: bytes, build_id: str = "") -> "Nso":
        """Build one from an already decompressed image (tests, patched images)."""
        nso = cls.__new__(cls)
        nso._init(bytes(image), build_id)
        return nso

    def _init(self, image: bytes, build_id: str) -> None:
        self.image, self.build_id = image, build_id
        self.mem = self.image[HEADER:]
        mem = self.mem
        mod0, = struct.unpack_from("<I", mem, 4)
        if mem[mod0:mod0 + 4] != b"MOD0":
            raise ValueError("MOD0 header not found")
        dyn = mod0 + struct.unpack_from("<i", mem, mod0 + 4)[0]
        tags = {}
        while True:
            t, v = struct.unpack_from("<qQ", mem, dyn); dyn += 16
            if t == 0:
                break
            tags[t] = v
        self.rela, self.rela_size = tags[7], tags[8]
        self.relocs: dict[int, int] = {}        # address of a pointer -> address it points to
        self.rela_entry: dict[int, int] = {}    # address of a pointer -> offset of its RELA entry
        for o in range(self.rela, self.rela + self.rela_size, 24):
            off, info, add = struct.unpack_from("<QQq", mem, o)
            if info & 0xFFFFFFFF == R_AARCH64_RELATIVE:
                self.relocs[off] = add
                self.rela_entry[off] = o

    def cstr(self, a: int) -> bytes:
        return self.mem[a:self.mem.index(b"\0", a)]

    def text(self, a: int) -> str:
        return self.cstr(a).decode("utf-8", "replace")

    def textish(self, a: int) -> bool:
        if not 0 <= a < len(self.mem):
            return False
        try:
            e = self.mem.index(b"\0", a)
            if e - a > 4000:
                return False
            self.mem[a:e].decode("utf-8")
            return True
        except (ValueError, UnicodeDecodeError):
            return False


def find_table(nso: Nso) -> tuple[int, int]:
    """``(address of the first slot, number of pointers)`` of the longest run of text pointers."""
    best = (0, 0)
    run_start = prev = None
    count = 0
    for p in sorted(nso.relocs):
        ok = nso.textish(nso.relocs[p])
        if ok and prev is not None and p == prev + 8 and run_start is not None:
            count += 1
        elif ok:
            run_start, count = p, 1
        else:
            run_start, count = None, 0
        prev = p
        if count > best[1]:
            best = (run_start, count)
    return best


def find_blocks(nso: Nso, t0: int, n: int) -> list[tuple[int, int, bool]]:
    """Blocks as ``(index of the first English row, rows, has a header)``, indices into the table."""
    ext = sorted((p, (a - t0) // 8) for p, a in nso.relocs.items()
                 if t0 <= a < t0 + 8 * n and not t0 <= p < t0 + 8 * n)
    groups, i = [], 0
    while i < len(ext):
        j = i
        while j + 1 < len(ext) and ext[j + 1][0] == ext[j][0] + 8:
            j += 1
        groups.append([e for _, e in ext[i:j + 1]]); i = j + 1
    four, heads = {}, set()
    for g in groups:
        if len(g) == 4:
            es = sorted(g)
            gaps = {es[k + 1] - es[k] for k in range(3)}
            if len(gaps) == 1:
                four[es[0]] = gaps.pop(); continue
        heads.update(g)
    bounds = sorted(heads | {e - 4 for e in four if e - 4 in heads} | {e for e in four if e - 4 not in heads} | {n})
    blocks = []
    for h in sorted(heads):
        en = h + 4
        if en in four:
            m = four[en]
        else:
            nxt = min(b for b in bounds if b > h)
            if (nxt - en) % 4:
                raise ValueError(f"block at {h} does not divide into four languages")
            m = (nxt - en) // 4
        blocks.append((en, m, True))
    blocks += [(en, m, False) for en, m in four.items() if en - 4 not in heads]
    blocks.sort()
    pos = 0
    for en, m, hdr in blocks:               # no gaps, no overlaps
        if (en - 4 if hdr else en) != pos:
            raise ValueError(f"blocks do not tile the table at {pos}")
        pos = en + 4 * m
    if pos != n:
        raise ValueError("blocks do not cover the whole table")
    return blocks


def rows(nso: Nso, t0: int, blocks) -> Iterator[dict]:
    """One dict per row with the four languages and the addresses of their pointers."""
    def slot(i):
        return t0 + 8 * i

    for bi, (en, m, hdr) in enumerate(blocks):
        for k in range(m):
            idx = [en + q * m + k for q in range(4)]
            yield {"block": bi, "row": k, "slots": [slot(i) for i in idx],
                   "en": nso.text(nso.relocs[slot(idx[0])]), "jp": nso.text(nso.relocs[slot(idx[1])]),
                   "kr": nso.text(nso.relocs[slot(idx[2])]), "tc": nso.text(nso.relocs[slot(idx[3])])}


def read_rows(nso: Nso) -> list[dict]:
    """Every row of the script of ``nso``."""
    t0, n = find_table(nso)
    return list(rows(nso, t0, find_blocks(nso, t0, n)))
