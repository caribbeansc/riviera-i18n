"""Writing translated strings into the executable: encoding, placement and the IPS patch.

For every row of the script with a translation the English string is replaced

* in place, if the new one fits and nobody else uses those bytes (shared or
  overlapping strings are moved instead), or
* in free space (the tails of strings that were shortened, and the Japanese,
  Korean and Chinese strings of the same rows, which are unused when the game runs
  in English) by changing the addend of the string's relocation.

Tags (``V(id)``, ``cN``) and separators are kept; the line breaks are recomputed by
:mod:`riviera.compose`.
"""

from __future__ import annotations

import bisect
import re
import struct

from .nso import HEADER

UNACCENT = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ¿¡", "aeiouunAEIOUUN?!")


def encode(text: str, mode: str = "ascii", strip_accents: bool = False) -> str:
    """Spanish text -> the game's convention. The ASCII comma separates segments, so the one in the text goes full-width."""
    if strip_accents:
        text = text.translate(UNACCENT)
    # The engine runs printf on a string BEFORE drawing it: an ASCII "%" followed by a space and a letter ("75% del")
    # is taken for a format and prints a number. The English writes percentages with a full-width "％"; only the
    # engine's own formats (%d, %s...) are left alone.
    text = re.sub(r"%(?!\d*[ds])", "％", text)
    out = []
    for ch in text:
        if ch == ",":
            out.append("，")
        elif ch == "…":
            out.append("＿")
        elif ch == "'":
            out.append("’")
        elif ch == '"':
            out.append("”")
        elif mode == "wide" and ch == " ":
            out.append("　")
        elif mode == "wide" and 0x21 <= ord(ch) <= 0x7E:
            out.append(chr(ord(ch) + 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


class Writes(dict):
    """offset -> bytes, refusing overlaps (checked only against the neighbours, in order)."""

    def __init__(self):
        super().__init__()
        self.starts: list[int] = []

    def put(self, off: int, data: bytes) -> None:
        i = bisect.bisect_left(self.starts, off)
        for o in self.starts[max(0, i - 1):i + 1]:
            if off < o + len(self[o]) and o < off + len(data):
                raise ValueError(f"overlapping writes at 0x{off:x} and 0x{o:x}")
        self.starts.insert(i, off)
        self[off] = bytes(data)


def to_ips(writes: dict, orig: bytes, gap: int = 4) -> bytes:
    """Serialise ``writes`` as an IPS patch, merging writes that are less than ``gap`` bytes apart."""
    recs: list[tuple[int, bytearray]] = []
    for off in sorted(writes):
        data = writes[off]
        if recs and off <= recs[-1][0] + len(recs[-1][1]) + gap:
            start, buf = recs[-1]
            if off > start + len(buf):
                buf += orig[start + len(buf):off]
            buf[off - start:off - start + len(data)] = data
        else:
            recs.append((off, bytearray(data)))
    out = bytearray(b"PATCH")
    for start, buf in recs:
        for i in range(0, len(buf), 0xFFFF):
            off, chunk = start + i, bytes(buf[i:i + 0xFFFF])
            if off == 0x454F46:                       # would look like the EOF marker
                off -= 1
                chunk = orig[off:off + 1] + chunk
            out += off.to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
    return bytes(out + b"EOF")


def apply_ips(ips: bytes, image: bytes) -> bytes:
    img, i = bytearray(image), 5
    if ips[:5] != b"PATCH":
        raise ValueError("not an IPS patch")
    while ips[i:i + 3] != b"EOF":
        off, size = int.from_bytes(ips[i:i + 3], "big"), int.from_bytes(ips[i + 3:i + 5], "big")
        img[off:off + size] = ips[i + 5:i + 5 + size]
        i += 5 + size
    return bytes(img)


def code_targets(nso) -> list[int]:
    """Addresses in ``.rodata`` that the CODE reaches directly (not through a relocation of the table): an
    ``adrp xN`` followed, within the next 16 instructions, by an ``add`` or a load/store with an offset on the same
    register. An upper bound: it may include too much, never too little for the loads the compiler emits. It exists so a
    string the code uses by itself is never rewritten or reused as free space (the "/" used to build file paths was
    once overwritten, and the game died three seconds after booting). Cached on the NSO.
    """
    if getattr(nso, "_code_targets", None) is not None:
        return nso._code_targets
    _, lo, size = struct.unpack_from("<III", nso.image, 0x10)
    words = struct.unpack_from("<%dI" % (size // 4), nso.mem, lo)
    out, n = set(), len(words)
    for i, w in enumerate(words):
        if (w & 0x9f000000) != 0x90000000:
            continue
        rd = w & 31
        imm = (((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3)
        if imm & (1 << 20):
            imm -= 1 << 21
        page = ((lo + 4 * i) & ~0xfff) + (imm << 12)
        for k in range(1, 17):
            if i + k >= n:
                break
            w2 = words[i + k]
            if (w2 >> 5) & 31 != rd:
                continue
            if (w2 & 0xff800000) == 0x91000000:                                   # add xd, xn, #imm
                off = ((w2 >> 10) & 0xfff) << (12 if (w2 >> 22) & 1 else 0)
                out.add(page + off)
            elif (w2 & 0x3b000000) == 0x39000000:                                 # ldr/str (unsigned offset)
                out.add(page + (((w2 >> 10) & 0xfff) << (w2 >> 30)))
    nso._code_targets = out = sorted(out)
    return out


def code_uses(nso, a: int, length: int) -> bool:
    """Does the code use directly the string that starts at ``a`` (``length`` bytes plus its zero)? It counts the exact
    start, the final zero (the empty string the linker merges) and an interior address that could be the merged tail of
    an ASCII string (previous byte ASCII and current byte printable). An access in the middle of a multi-byte UTF-8
    character (the table strings are full-width) is a false positive of the scan, not a string, and does not count."""
    t, mem = code_targets(nso), nso.mem
    i = bisect.bisect_left(t, a)
    while i < len(t) and t[i] <= a + length:
        x = t[i]
        if x == a or x == a + length or (mem[x - 1] < 0x80 and 0x20 <= mem[x] < 0x7F):
            return True
        i += 1
    return False


def place(nso, want: dict, extra_pool=()):
    """Decide where every new string goes. ``want``: slot -> (original address, new bytes).

    ``extra_pool``: free memory intervals ``(start, end)`` added to the ones the rewrite itself frees.
    Returns ``(writes, slot -> final address, relocated, without room, free intervals)``.
    """
    targets = sorted(set(nso.relocs.values()))
    users: dict[int, list[int]] = {}
    for slot, (a, _) in want.items():
        users.setdefault(a, []).append(slot)

    def inplace_ok(a: int, length: int) -> bool:
        if code_uses(nso, a, length):
            return False                                                      # the code uses these bytes directly
        i = bisect.bisect_right(targets, a)
        if i < len(targets) and targets[i] <= a + length:
            return False                                                      # another pointer points inside
        j = i - 2                                                             # the one before `a`
        if j >= 0 and nso.textish(targets[j]) and targets[j] + len(nso.cstr(targets[j])) >= a:
            return False
        return True

    writes, pool, placed, relocate = Writes(), list(extra_pool), {}, []
    for a, slots in users.items():
        length = len(nso.cstr(a))
        first_new = want[slots[0]][1]
        if inplace_ok(a, length) and len(first_new) <= length:
            writes.put(HEADER + a, first_new + b"\0")
            if length > len(first_new):
                pool.append((a + len(first_new) + 1, a + length + 1))
            for s in slots[:]:
                if want[s][1] == first_new:
                    placed[s] = a
            relocate += [s for s in slots if want[s][1] != first_new]
        else:
            relocate += slots
            if inplace_ok(a, length) and all(s in slots for s in users[a]):
                pool.append((a, a + length + 1))

    # relocate into free space: the longest first, into the tightest hole
    relocate.sort(key=lambda s: -len(want[s][1]))
    unplaced = []
    for s in relocate:
        data = want[s][1] + b"\0"
        best = min(((e - st, i) for i, (st, e) in enumerate(pool) if e - st >= len(data)), default=None)
        if best is None:
            unplaced.append(s)
            continue
        st, e = pool.pop(best[1])
        writes.put(HEADER + st, data)
        placed[s] = st
        if e - st > len(data):
            pool.append((st + len(data), e))
        writes.put(HEADER + nso.rela_entry[s] + 16, struct.pack("<q", st))

    return writes, placed, relocate, unplaced, pool
