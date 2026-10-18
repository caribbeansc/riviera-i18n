"""Write the script into the Android library, slot by slot.

Every pointer to a Japanese string of ``libapp.so`` (a *slot*) gets the text of its Switch row: the English the donor executable carries,
or the translation of the language pack composed for the real glyph widths (:mod:`riviera.compose`). The new strings go into one loadable
segment appended to the file (the ``PT_NOTE`` header is reused as its ``PT_LOAD``) and the relocation and the stored value of each slot
are redirected to them; the Japanese strings stay where they were. The segment starts with the room the hooks need
(:data:`riviera.android.hooks.RESERVE`), then comes the text.

Three more kinds of text are handled here:

* strings that only exist in the Android app (touch tutorials, the team-edit help, skill effects with numbers, zone names, cloud
  backup messages): ``langs/<code>/android/text.jsonl`` keyed by the fingerprint of the Japanese. They are composed like Switch text
  (segments and tags of the original, lines broken at the real widths, a ``%s`` measured as a three-digit number). Where the English
  of such a string is *the official English* the pack does not carry it: it carries a **reference** to the Switch string
  (:func:`resolve_entries`), which the build reads from the user's own dump;
* literals the code uses directly, with no pointer in a table (the native cloud-backup dialogs): rewritten in place, so they cannot be longer;
* a few plain ASCII labels the library already carries in English and that the PC and Switch builds write differently (``ENGLISH_FIXES``).
"""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .. import compose, font, ips, metrics, nso as nsomod, segments, workflow
from ..packs import LangPack, fingerprint, read_jsonl
from . import align as alignmod
from .elf import PF_R, PF_X, SEGMENT_ALIGN, Elf
from .hooks import RESERVE
from . import AndroidError

#: Width of a Japanese cell in engine units: the box of a text that only exists in Android is as wide as its longest Japanese line times this.
JP_CELL = 66
#: Engine clips dialogue lines about 12 % past the width English uses, so pages may be that much wider than the English box.
DEFAULT_SOFT = 1.12
#: ``_skl_efc_mes_sjis``: 16-byte entries ``{u32 swap, u32, char *format}`` of the skill effect descriptions (version 1.0.4).
SKILL_FLAGS = 0xa936f0
#: "X rises by %s for %s turns": the Japanese gives the turns first, the translations say the amount first, so the order flag is cleared.
SKILL_SWAP = range(0x23, 0x2e)

#: Plain ASCII labels the library already carries in English (so they never go through the Japanese table) and that the PC and Switch
#: builds spell differently, because the mode is called LOOK there and not QUEST. They are the five pointers of the label table the
#: field screen reads (moving / nothing to examine / - / - / looking). Both sides are given as the SHA-1 of the text, so no game text is
#: stored: ``{SHA-1 of the label in the library: SHA-1 of the label in the Switch executable}``.
ENGLISH_FIXES = {
    "641720314fdecb3d1945a1e6f3bd3b1f4f0ef8d0": "695f59808cd920a7358be23eb8125b1343c2c0b0",
    "b036430bd4dcde37a22d23b41a1d8d1e08fd3ce6": "45fa0669e0b7e14df53a6c769f656fb49ca0f466",
    "048a2aaf2a526cdf751e2e62926299483929257a": "ae234953ba480f19130b4a139adf821ff9c68ea6",
}


class TextError(AndroidError):
    """The text of the pack cannot be written into this library."""


# ----------------------------------------------------------- composition --

#: Blocks of interface text (explorations, menus, messages) whose boxes were designed for the English lines.
UI_BLOCKS = set(range(0, 10)) | {34, 37, 38, 39}


def rewrap_ui(rows, texts, M, factor=1.25) -> int:
    """Labels and messages of the interface whose **English has more than one line** (confirmation boxes, menu help): the box was designed for
    those lines, and a translation left on a single long line is cut at the edge of the Android box. Every segment with two or more English
    lines and a translated line wider than ``factor`` times the widest English one is split again into the same number of lines (balanced,
    with that cap, widened a little if it does not fit). Bullet lists are left alone (they are one bullet per line already)."""
    fixed = 0
    for g, raw in list(texts.items()):
        r = rows[g]
        if r["block"] not in UI_BLOCKS or "・" in raw:
            continue
        en = segments.split_segments(r["en"])
        tr = segments.split_segments(raw)
        if len(en) != len(tr):
            continue
        parts, changed = [], False
        for (_, _, te), (sep, pre, ts) in zip(en, tr):
            en_lines = [x for x in re.split(r";|\n", te) if segments.disp(x).strip()]
            tr_lines = [x for x in re.split(r";|\n", ts) if segments.disp(x).strip()]
            if len(en_lines) >= 2 and tr_lines:
                cap = factor * max(M.line(segments.disp(x)) for x in en_lines)
                if max(M.line(segments.disp(x)) for x in tr_lines) > cap:
                    words = " ".join(x.strip() for x in tr_lines)
                    new = None
                    for k in (1.0, 1.15, 1.3, 1.5):
                        cand = compose.wrap_units(words, cap * k, M)
                        if len(cand) <= len(en_lines):
                            new = cand
                            break
                    if new:
                        ts = ("\n" if "\n" in te else ";").join(new)
                        changed = True
            parts.append(sep + pre + ts)
        if changed:
            texts[g] = "".join(parts)
            fixed += 1
    return fixed


def rewrap_dialog(rows, texts, M, max_lines=2) -> int:
    """Dialogue (blocks 11-21 and 35): **no page goes past 2 lines**. The dialogue box and the message log are made for two lines and the
    English never exceeds them (18 064 pages: 9 595 of one line and 8 469 of two). Pages the composer left in three (the third line fell out
    of the bottom of the box, and in the log it overlapped the next entry) are split again into two, with the smallest cap that does it
    (balanced); the ones that then need more than the engine's box offers are drawn at a smaller scale by the hooks (``hk_msg_scale``)."""
    fixed = 0
    for g, raw in list(texts.items()):
        if rows[g]["block"] not in compose.SOFT_BLOCKS:
            continue
        parts, changed = [], False
        for sep, pre, ts in segments.split_segments(raw):
            lines = [x for x in re.split(r";|\n", ts) if segments.disp(x).strip()]
            if len(lines) > max_lines:
                words = [w for w in " ".join(x.strip() for x in lines).split(" ") if w]
                lo = max(M.line(ips.encode(w, "ascii", False)) for w in words)
                hi = 4000
                if len(compose.wrap_words(words, hi, M)) <= max_lines:
                    while hi - lo > 2:
                        mid = (lo + hi) // 2
                        if len(compose.wrap_words(words, mid, M)) <= max_lines:
                            hi = mid
                        else:
                            lo = mid
                    new = [" ".join(words[k] for k in ln) for ln in compose.wrap_words(words, hi, M)]
                    ts = re.match(r" *", ts).group() + ("\n" if "\n" in ts else ";").join(new)
                    changed = True
            parts.append(sep + pre + ts)
        if changed:
            texts[g] = "".join(parts)
            fixed += 1
    return fixed


def translated_texts(nso, rows, db, M, charset, soft: float, say=print):
    """``({row index: final string}, caps)`` of every row the pack translates, composed with ``compose.build_text`` and then adjusted to
    the Android boxes (:func:`rewrap_ui`, :func:`rewrap_dialog`). Rows without a translation do not appear (they keep the donor's English)."""
    want, overflow, skipped, _, caps = compose.build_text(nso, rows, db, M, charset, soft)
    by_slot = {r["slots"][0]: g for g, r in enumerate(rows)}
    out = {by_slot[s]: raw.decode("utf-8") for s, (_, raw) in want.items()}
    n_ui = rewrap_ui(rows, out, M)
    n_dlg = rewrap_dialog(rows, out, M)
    say(f"  script: {len(out)} rows translated, {len(overflow)} do not fit their box, {skipped} do not match the segments of the original, "
        f"{n_ui} interface rows kept to the English lines, {n_dlg} dialogue rows brought from 3 lines to 2")
    return out, caps


def compose_android(raw: str, parts: list[str], M, dialog_cap: int, soft: float, cap: int | None = None):
    """Final string of a text that exists only in Android. ``raw`` is the Japanese as the library stores it and ``parts`` the translated
    segments. Returns ``(string, warnings)``."""
    segs = segments.split_segments(raw)
    out, warns = [], []
    for (sep, prefix, orig), text in zip(segs, parts):
        jp_lines = re.split(r";|\n", orig)
        max_lines = len(jp_lines)
        talk = prefix.startswith("V(") or re.match(r"c\d", prefix)
        if cap:
            cap_s = cap
        elif talk:                                   # voices and tutorial notices: the full-width dialogue band
            max_lines, cap_s = max(2, max_lines), dialog_cap
        else:                                        # help boxes and labels: at most the width of the Japanese
            widest = max(len(re.sub(r"c\d|V\([^)]*\)", "", ln)) for ln in jp_lines)
            cap_s = widest * JP_CELL
        meas = text.replace("%s", "999")             # the numbers come from the engine: measured as three digits
        if M.line(ips.encode(meas, "ascii", False)) <= cap_s:
            lines = [meas]
        else:
            lines = compose.wrap_units(meas, cap_s, M)
            if len(lines) > max_lines and talk and soft > 1:
                alt = compose.wrap_units(meas, int(cap_s * soft), M)
                if len(alt) <= max_lines:
                    lines = alt
        lines = [ln.replace("999", "%s") for ln in lines]
        if len(lines) > max_lines:
            warns.append(f"{len(lines)} lines (max {max_lines}): {text[:50]}")
        wide = max(M.line(ips.encode(ln.replace("%s", "999"), "ascii", False)) for ln in lines)
        if wide > (cap_s * soft if talk else cap_s):
            warns.append(f"width {wide} > {cap_s}: {text[:50]}")
        joiner = "\n" if "\n" in orig else ";"
        out.append(sep + prefix + joiner.join(ips.encode(ln, "ascii", False) for ln in lines))
    return "".join(out), warns


def read_android_text(path) -> tuple[dict[str, dict], dict[str, dict]]:
    """``(texts, literals)`` of ``langs/<code>/android/text.jsonl``, each by fingerprint of the Japanese. Absent file: both empty.

    An entry carries its text in ``t`` (a list of segments) or, when that text is the official English, a reference to the Switch string:
    ``{"k": ..., "ref": fingerprint of the Switch string}`` for all its segments, or items ``{"ref": ..., "seg": n}`` inside ``t`` for
    some of them. The references are resolved by :func:`resolve_entries`."""
    texts, literals = {}, {}
    if Path(path).is_file():
        for o in read_jsonl(path):
            if "t" not in o and "ref" not in o:
                raise TextError(f"{path}: the entry {o.get('k')} has neither text (\"t\") nor a reference (\"ref\")")
            (literals if o.get("lit") else texts)[o["k"]] = o
    return texts, literals


def donor_units(rows) -> dict[str, list[str]]:
    """``{fingerprint of a Switch string: its readable segments}`` for every distinct string of the script (the English of the donor)."""
    return {k: u["en"] for k, u in workflow.units_of(rows).items()}


def resolve_entries(entries: dict[str, dict], units: dict[str, list[str]] | None) -> dict[str, dict]:
    """The entries with every reference replaced by the text it points to in the donor's script: afterwards each entry has ``t``, a list of
    strings. ``units`` is :func:`donor_units` of the user's Switch dump (``None`` if there is none, which fails for the first reference)."""
    def unit(ref: str, k: str) -> list[str]:
        if units is None:
            raise TextError(f"the entry {k} refers to the Switch script, and there is no Switch dump to read it from")
        if ref not in units:
            raise TextError(f"the entry {k} refers to a string ({ref}) that the Switch script of this dump does not have "
                            "(is it the supported version of the game?)")
        return units[ref]

    out = {}
    for k, o in entries.items():
        if "ref" in o:
            t = list(unit(o["ref"], k))
        else:
            t = []
            for item in o["t"]:
                if isinstance(item, dict):
                    segs = unit(item["ref"], k)
                    n = item.get("seg", 0)
                    if not 0 <= n < len(segs):
                        raise TextError(f"the entry {k} asks for segment {n} of a string that has {len(segs)}")
                    t.append(segs[n])
                else:
                    t.append(item)
        out[k] = {**{f: v for f, v in o.items() if f != "ref"}, "t": t}
    return out


def android_only_texts(slots, mapped: set[int], entries: dict[str, dict], M, caps, soft: float, say=print) -> list[tuple[int, str]]:
    """``[(slot, text)]`` for the Japanese slots without a counterpart in Switch that the pack translates. An entry marked ``force`` also
    replaces a slot that did align: its Japanese is identical to a Switch row, but the Switch text talks about physical buttons."""
    dialog_cap = caps[(12, "")][1]
    out, warns, left = [], [], 0
    for slot, raw in slots:
        o = entries.get(fingerprint(raw))
        if slot in mapped and not (o and o.get("force")):
            continue
        if o is None:
            left += 1
            continue
        n_jp = len(segments.split_segments(raw))
        if len(o["t"]) != n_jp:
            raise TextError(f"the text of the entry {fingerprint(raw)} has {len(o['t'])} segments and the original has {n_jp}")
        text, w = compose_android(raw, o["t"], M, dialog_cap, soft, o.get("cap"))
        out.append((slot, text))
        warns += w
    say(f"  android only: {len(out)} slots translated, {left} left (debug comments, character grids, staff names), {len(warns)} warnings")
    for w in sorted(set(warns))[:30]:
        say(f"    warning: {w}")
    return out


def android_literals(literals, entries: dict[str, dict]) -> dict[int, bytes]:
    """``{address: bytes}`` to write over the literals (strings the code uses directly) the pack translates. They are zero padded to the
    length of the Japanese, so a translation that does not fit is refused."""
    out = {}
    for addr, raw in literals:
        o = entries.get(fingerprint(raw))
        if o is None:
            continue
        new, old = o["t"][0].encode("utf-8"), raw.encode("utf-8")
        if len(new) > len(old):
            raise TextError(f"the literal at 0x{addr:x} needs {len(new)} bytes and has room for {len(old)}")
        out[addr] = new + b"\0" * (len(old) - len(new))
    return out


# ---------------------------------------------------------- english fixes --

_ASCII_STRING = re.compile(rb"[\x20-\x7e]{6,40}")


def _strings_by_hash(data: bytes, wanted: set[str]) -> dict[str, list[int]]:
    """Offsets of the NUL-delimited ASCII strings of ``data`` whose SHA-1 is in ``wanted``."""
    found: dict[str, list[int]] = {}
    pos = 0
    for chunk in data.split(b"\0"):
        if 6 <= len(chunk) <= 40 and _ASCII_STRING.fullmatch(chunk):
            h = hashlib.sha1(chunk).hexdigest()
            if h in wanted:
                found.setdefault(h, []).append(pos)
        pos += len(chunk) + 1
    return found


def english_fixes(elf: Elf, nso, relocs) -> list[tuple[int, str]]:
    """``[(slot, text)]`` redirecting the pointers to the labels of :data:`ENGLISH_FIXES` to the text the Switch executable has."""
    old = _strings_by_hash(bytes(elf.data), set(ENGLISH_FIXES))
    new = _strings_by_hash(nso.mem, set(ENGLISH_FIXES.values()))
    out = []
    for old_hash, new_hash in ENGLISH_FIXES.items():
        if len(old.get(old_hash, ())) != 1 or not new.get(new_hash):
            raise TextError("a label the field screen uses was not found exactly once in the library (a different version of the app?)")
        addr = elf.vaddr_of(old[old_hash][0])
        start = new[new_hash][0]
        text = nso.mem[start:nso.mem.index(b"\0", start)].decode("ascii")
        slots = sorted(s for s, (_, target) in relocs.items() if target == addr)
        if not slots:
            raise TextError("no pointer uses a label of the field screen (a different version of the app?)")
        out += [(s, text) for s in slots]
    return out


# ------------------------------------------------------------------- plan --

@dataclass
class TextPlan:
    #: ``(slot, text)`` in the order they are written: the aligned rows, the Android-only texts, the label fixes
    strings: list[tuple[int, str]] = field(default_factory=list)
    literals: dict[int, bytes] = field(default_factory=dict)
    swap_skill_order: bool = False
    stats: dict = field(default_factory=dict)


def plan(elf: Elf, nso, pack: LangPack, *, font_writes: dict | None = None, say=print) -> TextPlan:
    """Decide the text of every slot of the library for ``pack``. Nothing is written yet."""
    rows = nsomod.read_rows(nso)
    mem = elf.memory_image()
    alignment = alignmod.align_library(elf, rows, mem)
    say(f"  aligned {len(alignment.rows)} of {len(alignment.slots)} Japanese slots with the Switch script ({dict(alignment.how)})")
    soft = float(pack.platform("android").get("soft", DEFAULT_SOFT))
    db = pack.text()
    if font_writes:
        M, charset = font.font_metrics(nso, font_writes)
    else:
        M, charset = metrics.Metrics(nso), metrics.charset_of(nso)

    texts, caps = translated_texts(nso, rows, db, M, charset, soft, say) if db else ({}, compose.block_caps(rows, M))
    p = TextPlan()
    for slot, g in alignment.rows.items():
        p.strings.append((slot, texts.get(g, rows[g]["en"])))

    android_texts, android_lits = read_android_text(pack.path / "android" / "text.jsonl")
    if android_texts or android_lits:
        units = donor_units(rows)
        android_texts, android_lits = resolve_entries(android_texts, units), resolve_entries(android_lits, units)
        only = android_only_texts(alignment.slots, set(alignment.rows), android_texts, M, caps, soft, say)
        p.strings += only
        p.literals = android_literals(alignmod.android_literals(elf, mem), android_lits) if android_lits else {}
        p.swap_skill_order = bool(only)
        say(f"  literals used by the code: {len(p.literals)} rewritten in place")
    relocs = elf.relative_relocs()
    p.strings += english_fixes(elf, nso, relocs)
    p.stats = {"rows": len(alignment.rows), "slots": len(alignment.slots)}
    return p


# ----------------------------------------------------------------- write --

def apply(elf: Elf, p: TextPlan, say=print) -> tuple[int, int]:
    """Write the plan into the library: the strings in the appended segment (after the room for the hooks), the literals in place, the
    order flags of the skill effects. Returns ``(file offset, address)`` of the segment, where the hooks go."""
    seg_off, seg_va = elf.next_segment_address()
    relocs = elf.relative_relocs()
    blob = bytearray(RESERVE)
    placed: dict[str, int] = {}
    changed = skipped = 0
    for slot, text in p.strings:
        if slot not in relocs:
            skipped += 1
            continue
        if text not in placed:
            placed[text] = seg_va + len(blob)
            blob.extend(text.encode("utf-8") + b"\0")
        elf.set_pointer(slot, relocs[slot][0], placed[text])
        changed += 1
    for addr, raw in p.literals.items():
        elf.write(addr, raw)
    if p.swap_skill_order:
        for i in SKILL_SWAP:
            addr = SKILL_FLAGS + 16 * i
            if elf.u32(addr) != 1:
                raise TextError(f"_skl_efc_mes_sjis[0x{i:x}]: the order flag is not the expected one (a different version of the app?)")
            elf.write(addr, struct.pack("<I", 0))
    elf.data.extend(b"\0" * (seg_off - len(elf.data)))
    elf.data.extend(blob)
    elf.replace_note_with_load(seg_off, seg_va, len(blob), PF_R | PF_X, SEGMENT_ALIGN)
    say(f"  {changed} pointers updated ({skipped} skipped), {len(placed)} new strings, segment of {len(blob)} bytes at 0x{seg_va:x}")
    return seg_off, seg_va
