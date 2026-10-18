"""Match the Japanese strings of the Android library with the rows of the Switch script.

The Android app ships its script as Japanese strings in ``libapp.so``; the Switch executable has the same script in four languages,
English among them. Every pointer to a Japanese string of the library (an ``R_AARCH64_RELATIVE`` relocation) is a *slot*. The slots,
sorted by address, follow the same order as the rows of the Switch table (12 355 forward steps against 20 backward ones), so the
alignment is done by order:

1. anchors: slots whose Japanese text appears in exactly one Switch row; the longest increasing chain of them is kept (the few steps
   backwards are dropped);
2. the rest: a text that exists in several rows takes the first one after the last assigned row (and before the next anchor);
   one that is not identical in the Switch script stays unassigned. **Nothing is ever assigned by similarity**: an approximate
   match once paired Android's touch variants ("tap the screen") with the Switch row of "press the B1 button";
3. what has no reliable counterpart is text that only exists in Android and is translated apart (``langs/<code>/android/text.jsonl``).

Nothing here is stored: the Japanese comes from the user's library and the Switch rows from the user's executable.
"""

from __future__ import annotations

import bisect
import collections
import re
from dataclasses import dataclass, field

from .elf import Elf

#: Addresses of the library below which the script strings live (the text area of ``.rodata``); the strings the code uses directly start at 0x330000.
TEXT_LIMIT = 0x913000
LITERALS_START = 0x330000

#: Blocks of the Switch table that hold interface text (menus, messages, exploration labels).
UI_BLOCKS = {34, 37, 38, 39} | set(range(0, 10))


def is_japanese(s: str) -> bool:
    return any(ord(c) > 0x2E80 for c in s) or s.startswith("V(")


def _jp_char(c: str) -> bool:
    o = ord(c)
    return 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFFEF or o in (0x3000, 0x3001, 0x3002)


def android_slots(elf: Elf, mem: bytes | None = None, limit: int = TEXT_LIMIT) -> list[tuple[int, str]]:
    """``[(slot, Japanese text)]`` of every pointer to a Japanese string, sorted by slot address."""
    mem = mem if mem is not None else elf.memory_image()
    out = []
    for slot, (_, target) in sorted(elf.relative_relocs().items()):
        if not 0x1000 <= target < limit:
            continue
        try:
            s = mem[target:mem.index(b"\0", target)].decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if s and is_japanese(s):
            out.append((slot, s))
    return out


def android_literals(elf: Elf, mem: bytes | None = None, lo: int = LITERALS_START, limit: int = TEXT_LIMIT) -> list[tuple[int, str]]:
    """``[(address, text)]`` of the Japanese strings the code uses directly (``adrp`` + ``add``), with no pointer in a table: the cloud
    backup messages, loose labels and debug messages. Only what looks like text counts (at least one Japanese character and 90 % Japanese
    or ASCII) inside the string area of ``.rodata``."""
    mem = mem if mem is not None else elf.memory_image()
    targets = {t for _, t in elf.relative_relocs().values()}
    out = []
    for m in re.finditer(rb"[^\x00]{3,}", mem[:limit]):
        off = m.start()
        if off < lo or off in targets:
            continue
        try:
            t = m.group(0).decode("utf-8")
        except UnicodeDecodeError:
            continue
        if any(_jp_char(c) for c in t) and sum(_jp_char(c) or 32 <= ord(c) < 127 or c == "\n" for c in t) >= 0.9 * len(t):
            out.append((off, t))
    return out


def lis(vals: list[int]) -> list[int]:
    """Indices of the longest strictly increasing subsequence."""
    tails, idx, prev = [], [], [-1] * len(vals)
    for i, v in enumerate(vals):
        k = bisect.bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            idx.append(i)
        else:
            tails[k] = v
            idx[k] = i
        prev[i] = idx[k - 1] if k else -1
    res, i = [], idx[-1] if idx else -1
    while i >= 0:
        res.append(i)
        i = prev[i]
    return res[::-1]


def align(slots: list[tuple[int, str]], rows: list[dict]) -> list[tuple[int, str] | None]:
    """For each slot, ``(row index, how)`` or ``None``. ``how`` is ``exact``, ``order``, ``near``, ``content``, ``ui`` or ``first``."""
    jp2g: dict[str, list[int]] = collections.defaultdict(list)
    for g, r in enumerate(rows):
        jp2g[r["jp"]].append(g)
    n = len(slots)
    assign: list[tuple[int, str] | None] = [None] * n
    # 1. unique anchors and a monotonic chain
    uniq = [(i, jp2g[s][0]) for i, (_, s) in enumerate(slots) if len(jp2g.get(s, ())) == 1]
    chain = [uniq[k] for k in lis([g for _, g in uniq])]
    for i, g in chain:
        assign[i] = (g, "exact")
    anchors = [i for i, _ in chain]
    # 2. the rest, in order, between anchors
    last_g, a_ptr = -1, 0
    for i, (_, s) in enumerate(slots):
        if assign[i]:
            last_g = assign[i][0]
            continue
        while a_ptr < len(anchors) and anchors[a_ptr] < i:
            a_ptr += 1
        next_g = assign[anchors[a_ptr]][0] if a_ptr < len(anchors) else len(rows)
        cands = [g for g in jp2g.get(s, ()) if last_g < g < next_g]
        if cands:
            assign[i] = (cands[0], "order")
            last_g = cands[0]
    # 3. second pass: texts that are identical in Switch but outside the order window (arrays the Android build lays out in another
    #    order). The row nearest to the previous slot's is taken; failing that, the unique English, or an interface block before the first row.
    for i, (slot, s) in enumerate(slots):
        if assign[i] or s not in jp2g:
            continue
        cands = jp2g[s]
        english = {rows[g]["en"] for g in cands}
        prev = assign[i - 1][0] if i and assign[i - 1] and slot - slots[i - 1][0] <= 16 else None
        if prev is not None:
            near = sorted(cands, key=lambda g: (g <= prev, abs(g - prev)))
            if abs(near[0] - prev) <= 50:
                assign[i] = (near[0], "near")
                continue
        if len(english) == 1:
            assign[i] = (cands[0], "content")
            continue
        ui = [g for g in cands if rows[g]["block"] in UI_BLOCKS]
        assign[i] = ((ui or cands)[0], "ui" if ui else "first")
    return assign


@dataclass
class Alignment:
    #: slot address -> index of the Switch row (into the list returned by :func:`riviera.nso.read_rows`)
    rows: dict[int, int] = field(default_factory=dict)
    how: collections.Counter = field(default_factory=collections.Counter)
    #: every Japanese slot of the library, aligned or not, in address order
    slots: list[tuple[int, str]] = field(default_factory=list)

    @property
    def unmapped(self) -> list[int]:
        return [s for s, _ in self.slots if s not in self.rows]


def align_library(elf: Elf, rows: list[dict], mem: bytes | None = None) -> Alignment:
    """Align every Japanese slot of the library with the rows of the Switch script."""
    slots = android_slots(elf, mem)
    res = Alignment(slots=slots)
    for (slot, _), asg in zip(slots, align(slots, rows)):
        if asg:
            res.rows[slot] = asg[0]
            res.how[asg[1]] += 1
    return res
