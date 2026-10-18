"""Validate and convert the save files of *Riviera: The Promised Land* between its Switch, Android and PC builds.

The game (Sting's ``sge`` engine) keeps its saves in **one and the same format** on the Switch (v1.0.0), Android (v1.0.4) and
PC (v1.0.3) builds: the same file names and sizes, the same ``ver1.0.0`` header and the same integrity check, a plain byte sum.
There is no hash, no signature and no device or account id in them. So nothing is converted from one format into another.
This module reads the files, validates them the way the game does when it loads them, recalculates the checksums, normalises
the few things that depend on the platform and rebuilds the autosave rotation table that lives in ``SYSTEM.DAT``
(the guarantees it makes are SPEC-011).

File layout (everything little-endian; the payloads are plain copies of the game's global structures)::

    file          size    type  contents
    SYSTEM.DAT    0x1438  0     SysSramSys (0x11a0) @0x48, ConfigWork (0x20c) @0x11e8, autosave rotation table (60 bytes) @0x13f4
    AUTOnn.DAT    0x7110  3     nn = 00..59.  SysSramCont (0x70c0) @0x48 = [0x18 header][SysSramSave 0x6100 @0x60][bSys 0xfa8]
    STORYnn.DAT   0x6150  2     nn = 00..99.  SysSramSave (0x6100) @0x48
    AUTOnn.PNG, STORYnn.PNG     240x136 RGBA thumbnail (optional: without it the save list draws no picture for that slot)

Every ``.DAT`` is ``u32 sum | header (0x40) | payload | u32 0 | u32 sum``:

* ``sum`` is the sum of the bytes in ``[0x44, size - 8)`` modulo 2**32. It is stored at ``+0`` and at ``size - 4``; the game
  accepts the file when either copy matches. The header is *not* covered by it.
* The header (from ``+4``) is ``"2023(C)STING Riviera"`` (0x20 bytes), ``"ver1.0.0"`` (0xc bytes), the ``u32`` size of the file,
  the ``u32`` type and six ``u16``: year, month, day, hour, minute, second, in the device's local time. The "newest" autosave
  is decided from that date.

What the game checks when it loads a file is what ``verify`` checks: the magic, the version string, the size written in the
header and the checksum (``_Check_Save*``, 0x731500-0x7316d4 in the Android v1.0.4 ``libapp.so``; ``SAVE_Load*Data``,
0xbe210-0xbf000 in the Switch v1.0.0 ``main``). The game recomputes the rotation table of ``SYSTEM.DAT`` itself when it loads it,
from the header dates of ``AUTO00``-``AUTO59`` (newest first; on a tie the lowest slot wins), and a new autosave goes to the
slot after the newest one.

What the conversions normalise
------------------------------

* **The message log (LOG) of every AUTO/STORY is emptied** (count = 0, entries zeroed; ``--keep-log`` keeps it). The Switch build
  stores the speaker id of each log entry with bit ``0x20000000`` set; Android uses it as a table index as it is, so opening
  LOG on Android with such a save crashes the game (SIGSEGV in ``LIM_getCharaNo``; reproduced). Playing is not affected.
* **ConfigWork bit 23, "View Wide", exists only on Android.** It is cleared when the destination is a Switch.
* **The configuration travels with the save.** Watch bit 8, ``Controller B`` (the button layout): with it on, which is the
  factory default, B confirms and A is "Play Demo" on the title screen. To keep the *destination's* configuration and move only the
  progress, pass the destination's ``SYSTEM.DAT`` with ``--dest-system`` and add ``--keep-dest-config``; without
  ``--keep-dest-config`` only its View Wide setting is kept (when the destination is Android).
* The two checksums are recalculated, the padding before the trailing checksum is zeroed, and the rotation table of
  ``SYSTEM.DAT`` is rebuilt from the dates of the saves that are written.
* Thumbnails (``.PNG``) are copied as they are, after checking the chunk CRCs. A thumbnail whose ``.DAT`` is not written is dropped.

Nothing here modifies the input: conversions always write to a new folder, and the output is verified with the same code as
``verify`` before a single byte is written.

Where the saves live
--------------------

=========  ==================================================================================================================
Android    ``/data/data/jp.co.sting.riviera/files/savedata/``. The app's *private* folder: reaching it needs root, ``run-as``
           on a debuggable build, or an emulator image that gives you a root shell.
Ryujinx    ``<data>/bis/user/save/<saveId>/0`` and ``/1``: two copies, committed and working. With the emulator closed, replace
           both. ``<saveId>`` is the folder whose ``ExtraData0`` starts with the title id ``01007D6025CB6000`` (little-endian
           u64). Do not copy ``ExtraData0/1`` or ``saveMeta`` between emulators.
Eden       ``<data>/nand/user/save/0000000000000000/<UserID>/01007D6025CB6000/``: plain files. On an Android device the data
           folder of Eden is ``/sdcard/Android/data/dev.eden.eden_emulator/files/``.
=========  ==================================================================================================================

Any of those folders (or a parent of them) can be given as the input: see :func:`find_save_dir`.

Tested
------

* Seven real Switch autosaves (made in Ryujinx), converted with ``switch2android`` and loaded in Android v1.0.4 on an emulator:
  the save list with thumbnails, loading, the menu, Status, exploration, dialogue, an encounter and Item Select. The LOG screen
  works only because the log is emptied.
* Real Android autosaves (made on the emulator), converted with ``android2switch`` and loaded in Ryujinx: the save list with
  thumbnails, loading, Stage Start and the dialogue of the first scene.
* Saves read from Eden on an Android device pass ``verify``.

Not tested
----------

* Real Eden: the saves of an Eden on a phone were only read and verified, never replaced by converted ones, so
  ``switch2switch`` and the Eden folder layout are untested end to end.
* Anything on a physical phone: nothing has been put into the Android app of a real device.
* Manual ``STORY`` saves (there was no real sample) and saves made in the middle of a battle (``bSys``).
* Opening the LOG on Switch with a save from Android converted with ``--keep-log`` (by default the log is emptied).
* The PC build: its code uses the same names, sizes and constants, but nobody has run this against it.

Usage (``rpl saves`` is ``python rpl.py saves``)::

    rpl saves dump <folder|file> [--json] [-v | --verbose]
    rpl saves verify <folder> [--target switch|android] [--strict]
    rpl saves switch2android <source folder> <output folder> [options]
    rpl saves android2switch <source folder> <output folder> [options]
    rpl saves switch2switch  <source folder> <output folder> [options]     (Ryujinx <-> Eden: a validated copy)

    conversion options:
      --force             overwrite a non-empty output folder (only the files that look like saves are deleted)
      --dest-system FILE  the SYSTEM.DAT of the destination: its View Wide setting is kept
      --keep-dest-config  with --dest-system: keep the destination's whole configuration (options, volumes)
      --only-newest-auto  write only the newest autosave
      --no-story          leave the manual (STORY) saves out
      --skip-invalid      skip the files that do not validate instead of aborting
      --keep-log          keep the message log (it can crash the game on the other platform)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass

MAGIC = b"2023(C)STING Riviera"
VERSION = b"ver1.0.0"
HEADER_OFF = 4                   # SAVE_DATA_HEADER inside the file, after the leading checksum
SUM_START = 0x44                 # the checksum covers [0x44, end)
TITLE_ID = "01007D6025CB6000"    # Switch title id: the name of Eden's per-game save folder
YEAR_MIN, YEAR_MAX = 2000, 2100  # what a header date may look like before it is called implausible
MAX_SEARCH_DEPTH = 6             # how many folder levels below the given path find_save_dir() looks into


@dataclass(frozen=True)
class Kind:
    """One kind of ``.DAT`` file."""
    size: int            # size of the file
    type_id: int         # value of the type field of the header
    end: int             # where the padding before the trailing checksum starts (the checksum covers [0x44, end))
    base: int | None     # offset of SysSramSave inside the file (None for SYSTEM.DAT)
    slots: int           # how many files of this kind there can be (nn = 00..slots-1)


KINDS = {
    "SYSTEM": Kind(size=0x1438, type_id=0, end=0x1430, base=None, slots=1),
    "STORY": Kind(size=0x6150, type_id=2, end=0x6148, base=0x48, slots=100),
    "AUTO": Kind(size=0x7110, type_id=3, end=0x7108, base=0x60, slots=60),
}
RING_OFF, RING_LEN = 0x13F4, 60  # autosave rotation table in SYSTEM.DAT
CFG_OFF, CFG_LEN = 0x11E8, 0x20C  # ConfigWork in SYSTEM.DAT
SYS_OFF = 0x48                   # SysSramSys in SYSTEM.DAT
CFG_ANDROID_ONLY = 1 << 23       # ConfigWork bit 23 (IsConfigViewWide): an option that only exists on Android
LOG_OFF, LOG_ENTRIES, LOG_SIZE = 0x1588, 100, 0xBC  # message log (CBackLog) inside SysSramSave
LOG_COUNT = 0x5EF8               # u32 number of log entries, inside SysSramSave

NAME_RE = re.compile(r"^(?:(SYSTEM)|(AUTO|STORY)(\d\d))\.(DAT|PNG)$", re.I)

#: Bits of the first word of ConfigWork, named after the game's own CConfig::_pushConfig/_popConfig and IsConfig* functions.
CFG_BITS = {
    0: "LearnTeam", 1: "BattleItem", 2: "ItemSelect", 3: "GuageWt", 4: "EnemySkillWin", 5: "EnemyCutIn (inverted)",
    8: "ControllerB", 9: "three-state option (A)", 10: "three-state option (B)", 11: "option 0x63",
    12: "voice language (VOICE_setLanguage)", 13: "option 0x59", 14: "option 0x58 (inverted)", 15: "option 0x5b",
    16: "no MES_setSpeedUp", 17: "TimeLine", 18: "option 0x5c", 19: "ControllerView", 20: "option 0x64 (inverted)",
    21: "CatVoice", 22: "AtController", 23: "ViewWide (Android only)",
}
LEVELS = ["easy", "normal", "hard", "nightmare"]            # gamelevel[] of the executable
MODES = ["standard", "original", "freedom", "highlevel"]    # gamemode[]


class SaveError(Exception):
    """A problem to report to the user without a traceback: bad input, a refused output, an invalid option."""


# ----------------------------------------------------------------------------------------------- low-level helpers --

def u16(d, o: int) -> int:
    """The little-endian ``u16`` at offset ``o``."""
    return struct.unpack_from("<H", d, o)[0]


def u32(d, o: int) -> int:
    """The little-endian ``u32`` at offset ``o``."""
    return struct.unpack_from("<I", d, o)[0]


def checksum(d, end: int) -> int:
    """Sum of the bytes in ``[0x44, end)`` modulo 2**32 (what ``_Check_Save*`` computes)."""
    return sum(memoryview(d)[SUM_START:end]) & 0xFFFFFFFF


def classify(name: str) -> tuple[str, int, str] | None:
    """``(kind, slot, extension)`` of the name of a game file (``SYSTEM.DAT``, ``AUTO07.PNG``...; any case), or None."""
    m = NAME_RE.match(name)
    if not m:
        return None
    if m.group(1):
        return ("SYSTEM", 0, m.group(4).upper())
    return (m.group(2).upper(), int(m.group(3)), m.group(4).upper())


def canonical_name(kind: str, slot: int, ext: str) -> str:
    """The name the game gives that file: ``SYSTEM.DAT``, ``AUTO07.PNG``, ``STORY42.DAT``."""
    return f"SYSTEM.{ext}" if kind == "SYSTEM" else f"{kind}{slot:02d}.{ext}"


@dataclass(frozen=True)
class Header:
    """The SAVE_DATA_HEADER of a ``.DAT`` file."""
    magic: bytes
    version: bytes
    size: int
    type_id: int
    time: tuple[int, ...]    # year, month, day, hour, minute, second


def parse_header(d) -> Header:
    """Read the header of a ``.DAT`` (the file must be at least 0x44 bytes long)."""
    return Header(
        magic=bytes(d[HEADER_OFF:HEADER_OFF + 0x20]).split(b"\0")[0],
        version=bytes(d[HEADER_OFF + 0x20:HEADER_OFF + 0x2C]).split(b"\0")[0],
        size=u32(d, HEADER_OFF + 0x2C), type_id=u32(d, HEADER_OFF + 0x30),
        time=struct.unpack_from("<6H", d, HEADER_OFF + 0x34),
    )


def format_time(t) -> str:
    """``(2026, 10, 17, 12, 25, 16)`` -> ``"2026-10-17 12:25:16"``."""
    return "%04d-%02d-%02d %02d:%02d:%02d" % tuple(t)


def png_info(d: bytes) -> tuple[int | None, int | None, list[str]]:
    """``(width, height, problems)`` of a PNG: the signature, the CRC of every chunk, and that IHDR, IDAT and IEND are there."""
    problems = []
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None, ["bad PNG signature"]
    o, w, h, idat, iend = 8, None, None, False, False
    while o + 12 <= len(d):
        length, kind = struct.unpack_from(">I4s", d, o)
        if o + 12 + length > len(d):
            problems.append("truncated %r chunk" % kind)
            break
        if zlib.crc32(d[o + 4:o + 8 + length]) & 0xFFFFFFFF != struct.unpack_from(">I", d, o + 8 + length)[0]:
            problems.append("bad CRC in %r" % kind)
        if kind == b"IHDR" and o + 16 <= len(d):                     # (a damaged IHDR can be shorter than its fields)
            w, h = struct.unpack_from(">II", d, o + 8)
        if kind == b"IDAT":
            idat = True
        if kind == b"IEND":
            iend = True
            break
        o += 12 + length
    if w is None:
        problems.append("no IHDR")
    if not idat:
        problems.append("no IDAT")
    if not iend:
        problems.append("no IEND")
    return w, h, problems


def check_dat(kind: str, d: bytes) -> list[tuple[str, str]]:
    """``(level, text)`` for everything wrong with a ``.DAT``: ``E`` (the game rejects it) or ``W`` (odd, but the game loads it).

    Equivalent to the game's ``_Check_Save*``.
    """
    k = KINDS[kind]
    if len(d) != k.size:
        return [("E", "size %d (expected %d)" % (len(d), k.size))]
    out = []
    h = parse_header(d)
    if h.magic != MAGIC:
        out.append(("E", "magic %r" % h.magic))
    if h.version != VERSION:
        out.append(("E", "version %r (expected %r)" % (h.version, VERSION)))
    if h.size != k.size:
        out.append(("E", "size in the header 0x%x (expected 0x%x)" % (h.size, k.size)))
    if h.type_id != k.type_id:
        out.append(("W", "type %d (expected %d; the game does not check it when loading)" % (h.type_id, k.type_id)))
    s, head, tail = checksum(d, k.end), u32(d, 0), u32(d, k.end + 4)
    if s != head and s != tail:
        out.append(("E", "checksum 0x%x matches neither +0 (0x%x) nor the trailer (0x%x)" % (s, head, tail)))
    elif head != tail:
        out.append(("W", "the two checksums differ (+0=0x%x, trailer=0x%x); the game accepts either" % (head, tail)))
    if u32(d, k.end) != 0:
        out.append(("W", "the padding before the trailing checksum is not 0"))
    t = h.time
    if not (YEAR_MIN <= t[0] <= YEAR_MAX and 1 <= t[1] <= 12 and 1 <= t[2] <= 31 and t[3] < 24 and t[4] < 60 and t[5] < 62):
        out.append(("W", "implausible date in the header: %s" % (t,)))
    return out


# ------------------------------------------------------------------------------------------- reading a save folder --

@dataclass
class Entry:
    """One save file that has been read: ``name`` is the canonical name (``AUTO07.DAT``)."""
    name: str
    kind: str            # SYSTEM, AUTO or STORY
    slot: int
    ext: str             # DAT or PNG
    data: bytes
    path: str | None = None

    @classmethod
    def of(cls, name: str, data: bytes, path: str | None = None) -> Entry:
        kind, slot, ext = classify(name)
        return cls(name, kind, slot, ext, data, path)


def _read(path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _has_dat(folder: str) -> bool:
    try:
        return any((c := classify(n)) and c[2] == "DAT" for n in os.listdir(folder))
    except OSError:
        return False


def find_save_dir(path, _depth: int = 0) -> tuple[str, list[str]]:
    """Resolve what the user pointed at to the folder that holds the ``.DAT`` files: ``(folder, notes)``.

    Accepts the folder of the saves itself; the ``<saveId>`` folder of Ryujinx (``0``, the committed copy, is used, or ``1`` if
    that is all there is); or any parent of the Eden folder (``.../<UserID>/01007D6025CB6000``), down to ``MAX_SEARCH_DEPTH``
    levels, trying the title id folder first. A file is returned as it is. If nothing is found the path comes back unchanged.
    """
    path = os.fspath(path)
    if os.path.isfile(path):
        return path, []
    notes: list[str] = []
    if _has_dat(path):
        return path, notes
    for sub in ("0", "1"):
        p = os.path.join(path, sub)
        if _has_dat(p):
            notes.append("Ryujinx save folder: reading '%s' (the %s copy)" % (sub, "committed" if sub == "0" else "working"))
            return p, notes
    if _depth >= MAX_SEARCH_DEPTH or not os.path.isdir(path):
        return path, notes
    try:
        names = sorted(os.listdir(path), key=lambda n: (n.upper() != TITLE_ID, n))
    except OSError:
        return path, notes
    for n in names:                                                     # one level further down (Eden: <UserID>/<TitleID>)
        p = os.path.join(path, n)
        if os.path.isdir(p):
            found, found_notes = find_save_dir(p, _depth + 1)
            if os.path.isdir(found) and _has_dat(found):
                return found, notes + found_notes
    return path, notes


def read_dir(path) -> tuple[dict[str, Entry], list[str], list[str]]:
    """Read a save folder (or one file): ``({canonical name: Entry}, notes, names of the files that were ignored)``."""
    path = os.fspath(path)
    if os.path.isfile(path):
        c = classify(os.path.basename(path))
        if not c:
            raise SaveError("'%s' is not a Riviera save file" % path)
        n = canonical_name(*c)
        return {n: Entry(n, c[0], c[1], c[2], _read(path), path)}, [], []
    real, notes = find_save_dir(path)
    if not os.path.isdir(real):
        raise SaveError("no such folder: '%s'" % path)
    files: dict[str, Entry] = {}
    ignored: list[str] = []
    for n in sorted(os.listdir(real)):
        c = classify(n)
        if not c:
            ignored.append(n)
            continue
        cn = canonical_name(*c)
        if cn in files:
            notes.append("'%s' and '%s' are the same save; the first one is used" % (files[cn].name, n))
            continue
        files[cn] = Entry(cn, c[0], c[1], c[2], _read(os.path.join(real, n)), os.path.join(real, n))
    if real != path:
        notes.insert(0, "input resolved to %s" % real)
    return files, notes, ignored


# ------------------------------------------------------------------------------------------------------ decoding --

def item_count(d: bytes) -> int:
    """Items obtained, counted like the game's backup screen does (bit maps in SysSramSys at +0x48 and +0x5c)."""
    def bit(base: int, idx: int) -> int:
        return (d[SYS_OFF + base + (idx >> 3)] >> (idx & 7)) & 1
    n = 0
    for i in range(0x9B):
        if (i < 1 or i > 7) and i != 9 and bit(0x48, i):
            n += 1
    for i in range(0x4C):
        if any(bit(0x5C, i + s * 0x50) for s in range(3)):
            n += 1
    return n


def config_flags(d: bytes) -> int:
    """The first word of ConfigWork (see ``CFG_BITS``)."""
    return u32(d, CFG_OFF)


def decode_system(d: bytes) -> dict:
    """The interesting fields of ``SYSTEM.DAT``: the options (ConfigWork), what has been obtained, the rotation table."""
    f = config_flags(d)
    return dict(
        config_flags="0x%08x" % f,
        config_bits={CFG_BITS.get(b, "bit%d" % b): True for b in range(24) if f >> b & 1},
        config_flags2="0x%08x" % u32(d, CFG_OFF + 4),
        text_speed=d[CFG_OFF + 8], volume_bgm_se_voice=(d[CFG_OFF + 9], d[CFG_OFF + 10], d[CFG_OFF + 11]),
        config_c_d=(d[CFG_OFF + 0xC], d[CFG_OFF + 0xD]),
        game_cleared=bool(d[SYS_OFF + 0x17] & 1), last_save=d[SYS_OFF + 0x14], items=item_count(d),
        autosave_rotation=list(d[RING_OFF:RING_OFF + RING_LEN]),
    )


def decode_slot(kind: str, d: bytes) -> dict:
    """The interesting fields of an AUTO or STORY save (offsets are relative to SysSramSave)."""
    sb = KINDS[kind].base
    area, stage = d[sb + 0x21], d[sb + 0x22]
    party_n = d[sb + 0x60]
    level, mode = d[sb + 0xF65], d[sb + 0xF66]
    pt = tuple(d[sb + 0x18:sb + 0x1D])                 # days, hours, minutes, seconds, frames
    return dict(
        play_time="%03d:%02d:%02d" % (pt[0] * 24 + pt[1], pt[2], pt[3]), play_time_raw=pt,
        chapter_byte=d[sb + 0x20] + 1, area=area, stage=stage + 1,
        difficulty=LEVELS[level] if level < len(LEVELS) else level, mode=MODES[mode] if mode < len(MODES) else mode,
        after_clear=bool(d[sb + 0xF67]), autosave_type="0x%02x" % d[sb + 0xF68], log_messages=u32(d, sb + LOG_COUNT),
        score=u16(d, sb + 0x126C) * 100, party=list(d[sb + 0x61:sb + 0x61 + min(party_n, 6)]),
        thumbnail_by_map=(d[sb + 0xB8] == 0),
    )


def pointer_fields(kind: str, d: bytes) -> list[tuple[str, int, int]]:
    """``(name, offset, value)`` of the 8-byte fields that look like process addresses.

    They depend on the platform (the game rebuilds the party's ones when it loads) and are shown by ``dump -v``.
    """
    g = KINDS[kind].base + 0x18                         # gSys
    out = []
    fields = [("gSys+0x%x" % (0x10 + 8 * i), g + 0x10 + 8 * i) for i in range(7)] + \
             [("member%d.name" % i, g + 0x60 + 0xA8 * i) for i in range(6)]
    for name, off in fields:
        out.append((name, off, struct.unpack_from("<Q", d, off)[0]))
    return out


def platform_guess(v: int) -> str:
    """Which platform a process address comes from (the Switch maps the game low, Android high)."""
    if v == 0:
        return "null"
    if v >> 32 == 0 and 0x08000000 <= v < 0x10000000:
        return "Switch"
    if 0x6000000000 <= v < 0x8000000000:
        return "Android"
    return "?"


def newest_auto(files) -> int | None:
    """Slot of the autosave with the latest header date, or None. On a tie the first (lowest) slot wins, like the game."""
    best = None
    for s in range(KINDS["AUTO"].slots):
        e = files.get(canonical_name("AUTO", s, "DAT"))
        if e and len(e.data) == KINDS["AUTO"].size:
            t = parse_header(e.data).time
            if best is None or t > best[1]:
                best = (s, t)
    return best[0] if best else None


# ------------------------------------------------------------------------------------------------------------ dump --

def cmd_dump(args) -> int:
    files, notes, ignored = read_dir(args.path)
    rows = []
    for n, e in files.items():
        if e.ext == "PNG":
            w, h, problems = png_info(e.data)
            rows.append(dict(file=n, type="PNG", bytes=len(e.data), width=w, height=h, problems=problems))
            continue
        problems = check_dat(e.kind, e.data)
        r = dict(file=n, type=e.kind, bytes=len(e.data), problems=["%s: %s" % p for p in problems])
        if len(e.data) == KINDS[e.kind].size and parse_header(e.data).magic == MAGIC:
            r["date"] = format_time(parse_header(e.data).time)
            if e.kind == "SYSTEM":
                r["system"] = decode_system(e.data)
            else:
                r["slot"] = decode_slot(e.kind, e.data)
                if args.verbose:
                    r["pointers"] = [dict(field=nm, offset=hex(off), value="0x%x" % v, platform=platform_guess(v))
                                     for nm, off, v in pointer_fields(e.kind, e.data)]
        rows.append(r)
    rows.sort(key=lambda r: (r["file"] != "SYSTEM.DAT", r["file"]))
    na = newest_auto(files)
    if args.json:
        print(json.dumps(dict(notes=notes, ignored=ignored, newest_autosave=na, files=rows), indent=1))
        return 0
    for nt in notes:
        print("note:", nt)
    if ignored:
        print("ignored (not game saves):", ", ".join(ignored))
    for r in rows:
        if r["type"] == "PNG":
            print("%-13s %7d B  PNG %sx%s%s" % (r["file"], r["bytes"], r["width"] or "?", r["height"] or "?",
                                                "  " + "; ".join(r["problems"]) if r["problems"] else ""))
            continue
        line = "%-13s %7d B  %s" % (r["file"], r["bytes"], r.get("date", "?"))
        if "slot" in r:
            p = r["slot"]
            line += "  %s  area %s-%s  %s/%s  time %s  score %d  party %s" % (
                "*" if p["after_clear"] else " ", p["area"], p["stage"], p["difficulty"], p["mode"], p["play_time"], p["score"],
                p["party"])
            line += "  log %d" % p["log_messages"]
        print(line + ("   <<< " + "; ".join(r["problems"]) if r["problems"] else "   (checksum OK)"))
        if "system" in r:
            s = r["system"]
            print("    config %s  flags2 %s  text speed %d  BGM/SE/voice %s  c/d %s" % (
                s["config_flags"], s["config_flags2"], s["text_speed"], s["volume_bgm_se_voice"], s["config_c_d"]))
            print("    options on: " + ", ".join(s["config_bits"]))
            print("    game cleared: %s  last save: %d  items: %d" % (s["game_cleared"], s["last_save"], s["items"]))
            print("    autosave rotation (the first one is the newest): %s ..." % s["autosave_rotation"][:8])
        for p in r.get("pointers", []):
            print("      %-18s @%-7s %-20s %s" % (p["field"], p["offset"], p["value"], p["platform"]))
    if na is not None:
        print("newest autosave by date: AUTO%02d" % na)
    return 0


# ---------------------------------------------------------------------------------------------------------- verify --

def verify_files(files, target: str | None = None) -> list[tuple[str, str, str]]:
    """``[(level, file, text)]`` for everything wrong with a set of saves: ``E`` errors, ``W`` warnings, ``I`` information.

    ``target`` (``"switch"`` or ``"android"``) adds the problems that only matter on that platform.
    """
    out = []
    for n, e in files.items():
        if e.ext == "PNG":
            w, h, problems = png_info(e.data)
            for p in problems:
                out.append(("E", n, p))
            if (w, h) != (240, 136) and not problems:
                out.append(("W", n, "thumbnail %sx%s (the game saves 240x136)" % (w, h)))
            if e.kind == "SYSTEM" or e.slot >= KINDS[e.kind].slots:       # SYSTEM.PNG and AUTO60.PNG are never written
                out.append(("W", n, "not a file the game uses"))
            elif canonical_name(e.kind, e.slot, "DAT") not in files:
                out.append(("W", n, "thumbnail without its .DAT"))
            continue
        if e.kind != "SYSTEM" and e.slot >= KINDS[e.kind].slots:
            out.append(("E", n, "slot out of range (maximum %d)" % (KINDS[e.kind].slots - 1)))
        for lv, tx in check_dat(e.kind, e.data):
            out.append((lv, n, tx))
        if e.kind != "SYSTEM" and canonical_name(e.kind, e.slot, "PNG") not in files:
            out.append(("I", n, "no thumbnail (.PNG): the save list draws no picture for this slot"))
        if e.kind == "SYSTEM" and len(e.data) == KINDS["SYSTEM"].size:
            if target == "switch" and config_flags(e.data) & CFG_ANDROID_ONLY:
                out.append(("W", n, "config bit 23 (View Wide, Android only) is on: it does nothing on Switch; "
                                    "`android2switch` clears it"))
            want = ring_for(files)
            if want is not None and list(e.data[RING_OFF:RING_OFF + RING_LEN]) != want:
                out.append(("I", n, "the rotation table does not match the dates of the AUTO files "
                                    "(the game recomputes it on load)"))
    if "SYSTEM.DAT" not in files:
        out.append(("W", "-", "there is no SYSTEM.DAT: the game starts from the default configuration and progress"))
    if not any(e.kind != "SYSTEM" and e.ext == "DAT" for e in files.values()):
        out.append(("W", "-", "there is no save game (AUTO/STORY)"))
    return out


def cmd_verify(args) -> int:
    files, notes, ignored = read_dir(args.path)
    for nt in notes:
        print("note:", nt)
    if ignored:
        print("ignored (not game saves):", ", ".join(ignored))
    problems = verify_files(files, args.target)
    for lv, n, tx in problems:
        print("%s  %-13s %s" % (lv, n, tx))
    n_err = sum(1 for p in problems if p[0] == "E")
    n_warn = sum(1 for p in problems if p[0] == "W")
    n_dat = sum(1 for e in files.values() if e.ext == "DAT")
    print("%d .DAT files, %d .PNG files: %d errors, %d warnings" % (n_dat, len(files) - n_dat, n_err, n_warn))
    return 1 if n_err or (args.strict and n_warn) else 0


# ------------------------------------------------------------------------------------------------------- conversion --

def ring_for(files) -> list[int] | None:
    """The rotation table the game would rebuild: the newest AUTO first, then downwards, wrapping from 0 to 59."""
    best = newest_auto(files)
    if best is None:
        return None
    out, v = [], best
    for _ in range(RING_LEN):
        out.append(v)
        v = v - 1 if v >= 1 else RING_LEN - 1
    return out


def log_entries(kind: str, d: bytes) -> int:
    """How many messages the log of an AUTO/STORY holds."""
    return u32(d, KINDS[kind].base + LOG_COUNT)


def clear_log(kind: str, d: bytes) -> bytes:
    """Empty the message log: count to 0 and the entries to 0 (the game only reads the first ``count`` of them)."""
    sb = KINDS[kind].base
    d = bytearray(d)
    struct.pack_into("<I", d, sb + LOG_COUNT, 0)
    d[sb + LOG_OFF:sb + LOG_OFF + LOG_ENTRIES * LOG_SIZE] = bytes(LOG_ENTRIES * LOG_SIZE)
    return bytes(d)


def refresh(kind: str, d: bytes) -> bytes:
    """Zero the padding before the trailing checksum and recalculate both copies of the checksum."""
    d = bytearray(d)
    k = KINDS[kind]
    struct.pack_into("<I", d, k.end, 0)
    s = checksum(d, k.end)
    struct.pack_into("<I", d, 0, s)
    struct.pack_into("<I", d, k.end + 4, s)
    return bytes(d)


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _is_within(path: str, folder: str) -> bool:
    """True if ``path`` is ``folder`` or lies below it. Compared by identity too, so another spelling (a different case on a
    file system that ignores it, a link) does not fool the check."""
    while True:
        if _same_file(path, folder):
            return True
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent


def _check_output_folder(src: str, dst: str, force: bool) -> None:
    """The output is always a new folder: never the input, inside it or around it; and never over other files without ``force``."""
    real_in = os.path.realpath(find_save_dir(src)[0])
    real_out = os.path.realpath(dst)
    norm_in, norm_out = os.path.normcase(real_in), os.path.normcase(real_out)
    if (norm_out == norm_in or norm_out.startswith(norm_in + os.sep) or norm_in.startswith(norm_out + os.sep)
            or _is_within(real_out, real_in) or _is_within(real_in, real_out)):
        raise SaveError("the output ('%s') cannot be the input folder, inside it or around it: "
                        "a conversion always writes to a new folder" % dst)
    if os.path.exists(dst) and os.listdir(dst) and not force:
        raise SaveError("'%s' already exists and is not empty (use --force to overwrite it)" % dst)


def _validate_input(files: dict[str, Entry], skip_invalid: bool) -> dict[str, Entry]:
    """The files that validate. The others abort the conversion, or are skipped (and reported) with ``skip_invalid``."""
    keep: dict[str, Entry] = {}
    skipped = []
    for n, e in files.items():
        if e.ext == "PNG":
            _, _, problems = png_info(e.data)
            if problems:
                skipped.append((n, "invalid PNG: " + "; ".join(problems)))
            else:
                keep[n] = e
            continue
        errors = [t for lv, t in check_dat(e.kind, e.data) if lv == "E"]
        if e.kind != "SYSTEM" and e.slot >= KINDS[e.kind].slots:
            errors.append("slot out of range")
        if errors:
            skipped.append((n, "; ".join(errors)))
        else:
            keep[n] = e
    if skipped and not skip_invalid:
        for n, why in skipped:
            print("ERROR  %s: %s" % (n, why))
        raise SaveError("the input does not validate (use --skip-invalid to leave those files out)")
    for n, why in skipped:
        print("skipped  %s: %s" % (n, why))
    return keep


def _select(keep: dict[str, Entry], no_story: bool, only_newest_auto: bool) -> dict[str, Entry]:
    if no_story:
        keep = {n: e for n, e in keep.items() if e.kind != "STORY"}
    if only_newest_auto:
        newest = newest_auto(keep)
        keep = {n: e for n, e in keep.items() if e.kind != "AUTO" or e.slot == newest}
    # a thumbnail without its .DAT is of no use
    return {n: e for n, e in keep.items() if e.ext == "DAT" or canonical_name(e.kind, e.slot, "DAT") in keep}


def _normalise_system(data: bytes, target: str, dest_system: str | None, keep_dest_config: bool, changes: list[str]) -> bytes:
    """SYSTEM.DAT: the View Wide bit and, with the destination's SYSTEM.DAT, the destination's configuration."""
    d = bytearray(data)
    flags = config_flags(d)
    new = flags & ~CFG_ANDROID_ONLY
    if dest_system:
        dest = _read(dest_system)
        if any(lv == "E" for lv, _ in check_dat("SYSTEM", dest)):
            raise SaveError("--dest-system does not validate (run `verify` on its folder)")
        if keep_dest_config:
            d[CFG_OFF:CFG_OFF + CFG_LEN] = dest[CFG_OFF:CFG_OFF + CFG_LEN]
            changes.append("SYSTEM.DAT: ConfigWork (options, volumes, menu state) taken from the destination")
            new = flags = config_flags(d)
        elif target == "android":
            new |= config_flags(dest) & CFG_ANDROID_ONLY
    if target == "switch":
        new &= ~CFG_ANDROID_ONLY
    if new != flags:
        changes.append("SYSTEM.DAT: config 0x%08x -> 0x%08x (bit 23, View Wide, exists only on Android)" % (flags, new))
    struct.pack_into("<I", d, CFG_OFF, new)
    return bytes(d)


def _normalise(keep: dict[str, Entry], target: str, dest_system: str | None, keep_dest_config: bool, keep_log: bool,
               changes: list[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for n, e in keep.items():
        if e.ext == "PNG":
            result[n] = e.data
            continue
        d = e.data
        if e.kind == "SYSTEM":
            d = _normalise_system(d, target, dest_system, keep_dest_config, changes)
        if e.kind != "SYSTEM" and not keep_log:
            n_log = log_entries(e.kind, d)
            if n_log:
                d = clear_log(e.kind, d)
                changes.append("%s: message log (LOG) emptied (%d entries)" % (n, n_log))
        out = refresh(e.kind, d)
        if out != e.data and e.kind != "SYSTEM" and not any(c.startswith(n + ":") for c in changes):
            changes.append("%s: checksums recalculated" % n)
        result[n] = out
    return result


def _rebuild_ring(result: dict[str, bytes], changes: list[str]) -> None:
    """Rewrite the rotation table of SYSTEM.DAT with the dates of the AUTO files that are being written."""
    if "SYSTEM.DAT" not in result:
        print("warning: the output has no SYSTEM.DAT (the destination will keep its own or use the factory default)")
        return
    ring = ring_for({n: Entry.of(n, d) for n, d in result.items() if n.startswith("AUTO") and n.endswith(".DAT")})
    if ring is None:
        return
    d = bytearray(result["SYSTEM.DAT"])
    if list(d[RING_OFF:RING_OFF + RING_LEN]) != ring:
        d[RING_OFF:RING_OFF + RING_LEN] = bytes(ring)
        changes.append("SYSTEM.DAT: rotation table -> AUTO%02d first" % ring[0])
    result["SYSTEM.DAT"] = refresh("SYSTEM", bytes(d))


def convert(src, dst, *, source: str, target: str, force: bool = False, dest_system: str | None = None,
            keep_dest_config: bool = False, only_newest_auto: bool = False, no_story: bool = False,
            skip_invalid: bool = False, keep_log: bool = False) -> int:
    """Validate the saves in ``src`` and write the ones for ``target`` (``"switch"`` or ``"android"``) into the new folder ``dst``.

    ``source`` (``"switch"`` or ``"android"``) is only used in the report. Prints what it does; raises :class:`SaveError` when
    the input or the options are wrong, in which case nothing has been written. Returns 0.
    """
    src, dst = os.fspath(src), os.fspath(dst)
    if keep_dest_config and not dest_system:
        raise SaveError("--keep-dest-config needs --dest-system")
    files, notes, ignored = read_dir(src)
    for nt in notes:
        print("note:", nt)
    if ignored:
        print("ignored:", ", ".join(ignored))
    _check_output_folder(src, dst, force)
    keep = _select(_validate_input(files, skip_invalid), no_story, only_newest_auto)

    changes: list[str] = []
    result = _normalise(keep, target, dest_system, keep_dest_config, keep_log, changes)
    _rebuild_ring(result, changes)

    # verify what was produced with the same code as `verify`, and only then write
    out_entries = {n: Entry.of(n, d) for n, d in result.items()}
    errors = [p for p in verify_files(out_entries, target) if p[0] == "E"]
    if errors:
        for _, n, tx in errors:
            print("internal error  %s: %s" % (n, tx))
        raise SaveError("the output does not validate (nothing is written)")
    os.makedirs(dst, exist_ok=True)
    if force:
        for n in os.listdir(dst):
            if classify(n):
                os.remove(os.path.join(dst, n))
    for n, d in sorted(result.items()):
        with open(os.path.join(dst, n), "wb") as f:
            f.write(d)
    for c in changes:
        print("change:", c)
    print("%s -> %s: %d files written to %s (source: %s)" % (source, target, len(result), dst, src))
    newest = newest_auto(out_entries)
    if newest is not None:
        print("newest autosave: AUTO%02d" % newest)
    print("Install them by replacing the WHOLE save folder of the destination (delete the old AUTO/STORY files first: an old slot "
          "with a later date would win as the \"newest\").")
    return 0


# ----------------------------------------------------------------------------------------------------------- CLI --

#: command -> (platform of the source saves, platform of the output)
CONVERSIONS = {
    "switch2android": ("switch", "android"),
    "android2switch": ("android", "switch"),
    "switch2switch": ("switch", "switch"),
}

EXAMPLES = """\
examples:
  rpl saves dump "<save folder>"
  rpl saves verify "<save folder>" --target android
  rpl saves switch2android "<Ryujinx save folder>" converted
  rpl saves android2switch "<folder from the phone>" converted --dest-system "<current SYSTEM.DAT>" --keep-dest-config

The input is never modified: a conversion writes a new folder. Close the emulator or the app, and back up the destination's
current saves, before you copy the result over them.
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rpl saves", epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Validate and convert Riviera: The Promised Land saves between Switch (Ryujinx / Eden), Android and PC.")
    sub = ap.add_subparsers(dest="command", metavar="command", required=True)

    p = sub.add_parser("dump", help="decode a save folder or a single save file")
    p.add_argument("path", help="a save folder, the <saveId> folder of Ryujinx, a parent of Eden's folder, or one file")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("-v", "--verbose", action="store_true", help="also show the fields that hold process addresses")

    p = sub.add_parser("verify", help="check what the game checks when it loads (exit code 1 if there are errors)")
    p.add_argument("path", help="a save folder, the <saveId> folder of Ryujinx, a parent of Eden's folder, or one file")
    p.add_argument("--target", choices=["switch", "android"], help="also report what only matters on that platform")
    p.add_argument("--strict", action="store_true", help="exit with 1 on warnings too")

    convert_options = argparse.ArgumentParser(add_help=False)
    convert_options.add_argument("src", help="the folder with the saves to convert (it is never modified)")
    convert_options.add_argument("dst", help="the NEW folder to write the converted saves into")
    convert_options.add_argument("--force", action="store_true", help="overwrite a non-empty output folder")
    convert_options.add_argument("--dest-system", metavar="SYSTEM.DAT",
                                 help="the SYSTEM.DAT of the destination: for an Android destination its View Wide setting is kept")
    convert_options.add_argument("--keep-dest-config", action="store_true",
                                 help="with --dest-system: keep the destination's whole configuration (options, volumes); "
                                      "only the progress travels")
    convert_options.add_argument("--only-newest-auto", action="store_true", help="write only the newest autosave")
    convert_options.add_argument("--no-story", action="store_true", help="leave the manual (STORY) saves out")
    convert_options.add_argument("--skip-invalid", action="store_true",
                                 help="skip the files that do not validate instead of aborting")
    convert_options.add_argument("--keep-log", action="store_true",
                                 help="keep the message log (LOG): it can crash the game on the other platform")
    for name, help_text in (("switch2android", "prepare Switch saves (Ryujinx / Eden) for Android"),
                            ("android2switch", "prepare Android saves for Switch (Ryujinx / Eden)"),
                            ("switch2switch", "a safe Ryujinx <-> Eden copy (same format: validates and normalises)")):
        sub.add_parser(name, help=help_text, parents=[convert_options])
    return ap


def main(argv: list[str] | None = None) -> int:
    """Run the command line. Returns the exit code: 0 all good, 1 problems found or the operation failed, 2 bad usage."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:                    # argparse exits on --help (0) and on a usage error (2)
        return e.code if isinstance(e.code, int) else 1
    try:
        if args.command == "dump":
            return cmd_dump(args)
        if args.command == "verify":
            return cmd_verify(args)
        source, target = CONVERSIONS[args.command]
        return convert(args.src, args.dst, source=source, target=target, force=args.force, dest_system=args.dest_system,
                       keep_dest_config=args.keep_dest_config, only_newest_auto=args.only_newest_auto,
                       no_story=args.no_story, skip_invalid=args.skip_invalid, keep_log=args.keep_log)
    except (SaveError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
