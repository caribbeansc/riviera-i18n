"""SPEC-011: the save-game converter (``riviera.saves``).

Every save in this file is synthetic: random bytes laid out like the real files (name, size, header, checksums, a few known
fields), built here from the format and not with the code under test. Nothing comes from the game.
"""

# Requirements assumed for SPEC-011. docs/specs/SPEC-011-saves.md is to be written from this list (one bullet each, same words):
#
# - **R-1** A `.DAT` is `u32 sum | header | payload | u32 0 | u32 sum`. The sum is the byte sum of `[0x44, size - 8)` modulo
#   2^32 (the header is not covered) and is stored at `+0` and at `size - 4`. The header holds the magic, the version, the size
#   of the file, the type and a date.
# - **R-2** Save files are `SYSTEM`, `AUTO00`-`59` and `STORY00`-`99` with `.DAT` or `.PNG`, in any case. Any other file is not
#   a save: it is left alone and listed as ignored.
# - **R-3** `verify` rejects what the game rejects (wrong size, magic, version or size in the header; a checksum that matches
#   neither copy; a slot out of range) and only warns about what the game tolerates (the type, copies that differ, padding that
#   is not zero, an implausible date). Either copy of the checksum is enough.
# - **R-4** Thumbnails are checked (signature, chunk CRCs, IHDR/IDAT/IEND). A size other than 240x136 and a thumbnail without
#   its `.DAT` are warnings; a `.DAT` without a thumbnail is information.
# - **R-5** The input may be the save folder itself, the `<saveId>` folder of Ryujinx (copy `0`, else `1`), any parent of Eden's
#   `<UserID>/<TitleID>` folder (the title folder first, within a bounded depth) or a single file. A path that does not exist is
#   an error.
# - **R-6** `dump` only reads. It summarises every slot and the system file, and offers `--json` and `-v` (the fields that hold
#   process addresses). It reports damaged files and still succeeds.
# - **R-7** A conversion never modifies its input and always writes a new folder: never the input, inside it or around it. A
#   non-empty output is refused without `--force`, which removes only files that look like saves. Valid thumbnails are copied as
#   they are; a thumbnail whose `.DAT` is not written is dropped.
# - **R-8** The message log of every AUTO/STORY is emptied (count 0, entries zeroed) unless `--keep-log`; nothing else in the
#   payload changes.
# - **R-9** ConfigWork bit 23 (View Wide, Android only) is cleared when the destination is Switch; for Android it comes from
#   `--dest-system`. `--keep-dest-config` copies the destination's whole ConfigWork and needs `--dest-system`; an invalid
#   `--dest-system` aborts. Otherwise the configuration travels with the save (Controller B included).
# - **R-10** The rotation table of `SYSTEM.DAT` is rebuilt from the header dates of the AUTO saves that are written: the newest
#   first, then downwards and wrapping from 0 to 59, the lowest slot winning a tie. `verify` reports a stale table as
#   information. With no AUTO save the table is left as it is.
# - **R-11** `--only-newest-auto` and `--no-story` select what is written. A file that does not validate aborts the conversion,
#   or is skipped and reported with `--skip-invalid`.
# - **R-12** Both copies of the checksum and the padding are recalculated on output.
# - **R-13** The output is verified before anything is written; if it does not validate, nothing is written.
# - **R-14** `main(argv)` returns 0 on success, 1 when there are errors or the operation fails (the message goes to stderr, with
#   no traceback) and 2 on a usage error. `verify --strict` fails on warnings too.
# - **R-15** The module needs nothing but the standard library, so it runs where Pillow is not installed.

from __future__ import annotations

import functools
import hashlib
import json
import random
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from riviera import saves as S

ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------------------------------------ the format, as data --

SIZE = {"SYSTEM": 0x1438, "AUTO": 0x7110, "STORY": 0x6150}
TYPE = {"SYSTEM": 0, "AUTO": 3, "STORY": 2}
BASE = {"AUTO": 0x60, "STORY": 0x48}              # where SysSramSave starts in the file
CFG = 0x11E8                                      # ConfigWork; its first word holds the option bits
CFG_LEN = 0x20C
RING = 0x13F4                                     # the autosave rotation table: 60 bytes
SYS = 0x48                                        # SysSramSys
LOG = 0x1588                                      # message log, relative to SysSramSave: 100 entries of 0xBC bytes...
LOG_LEN = 100 * 0xBC
LOG_COUNT = 0x5EF8                                # ...and the u32 count
CONTROLLER_B = 1 << 8
VIEW_WIDE = 1 << 23                               # exists only on Android
DEFAULT_FLAGS = 0x002FA907                        # the factory default (Controller B on)
MAGIC = b"2023(C)STING Riviera"


def end_of(kind: str) -> int:
    """Where the padding before the trailing checksum starts."""
    return SIZE[kind] - 8


def seal(d: bytearray, kind: str) -> bytes:
    """Zero the padding and write both copies of the checksum."""
    end = end_of(kind)
    d[end:end + 4] = bytes(4)
    s = sum(d[0x44:end]) & 0xFFFFFFFF
    d[0:4] = struct.pack("<I", s)
    d[end + 4:end + 8] = struct.pack("<I", s)
    return bytes(d)


def expected_ring(newest: int) -> list[int]:
    return [(newest - i) % 60 for i in range(60)]


def make_dat(kind: str, *, when=(2026, 10, 17, 12, 0, 0), seed: int = 0, log: int = 0, flags: int = DEFAULT_FLAGS,
             ring: list[int] | None = None, level: int = 1, mode: int = 0, score: int = 22, play=(0, 1, 2, 3, 0),
             party=(0, 5), area: int = 1, stage: int = 0, text_speed: int = 4, volumes=(60, 70, 80)) -> bytes:
    """A valid synthetic ``.DAT``: random payload with the header, the known fields and both checksums in place."""
    d = bytearray(random.Random(seed).randbytes(SIZE[kind]))
    d[4:0x24] = MAGIC.ljust(0x20, b"\0")
    d[0x24:0x30] = b"ver1.0.0".ljust(0xC, b"\0")
    struct.pack_into("<II", d, 0x30, SIZE[kind], TYPE[kind])
    struct.pack_into("<6H", d, 0x38, *when)
    d[0x44:0x48] = bytes(4)
    if kind == "SYSTEM":
        struct.pack_into("<I", d, CFG, flags)
        d[CFG + 8:CFG + 12] = bytes([text_speed, *volumes])
        d[CFG + 0xC:CFG + 0xE] = bytes([3, 1])
        d[SYS + 0x14] = 2                                  # last save
        d[SYS + 0x17] = 0                                  # game not cleared
        d[RING:RING + 60] = bytes(ring if ring is not None else expected_ring(0))
    else:
        sb = BASE[kind]
        d[sb + 0x18:sb + 0x1D] = bytes(play)
        d[sb + 0x20], d[sb + 0x21], d[sb + 0x22] = 0, area, stage
        d[sb + 0x60] = len(party)
        d[sb + 0x61:sb + 0x61 + len(party)] = bytes(party)
        d[sb + 0xF65], d[sb + 0xF66], d[sb + 0xF67], d[sb + 0xF68] = level, mode, 0, 1
        struct.pack_into("<H", d, sb + 0x126C, score)
        d[sb + LOG:sb + LOG + LOG_LEN] = bytes(LOG_LEN)
        for i in range(log):                               # the speaker id has bit 0x20000000 set, as the Switch writes it
            off = sb + LOG + i * 0xBC
            d[off:off + 0xB8] = bytes(1 + (i + j) % 250 for j in range(0xB8))
            struct.pack_into("<I", d, off + 0xB8, 0x20000000 + i)
        struct.pack_into("<I", d, sb + LOG_COUNT, log)
    return seal(d, kind)


@functools.lru_cache(maxsize=None)
def make_png(width: int = 240, height: int = 136) -> bytes:
    """A valid RGBA PNG written by hand: signature, IHDR, one IDAT, IEND."""
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(width * 4) for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def patched(d: bytes, offset: int, data: bytes) -> bytes:
    b = bytearray(d)
    b[offset:offset + len(data)] = data
    return bytes(b)


def save_set(*, autos=(0, 1, 2), story=(0,), log: int = 4, flags: int = DEFAULT_FLAGS, system: bool = True, thumbs: bool = True,
             ring: list[int] | None = None) -> dict[str, bytes]:
    """A complete set of synthetic saves. AUTO slot ``n`` is one hour newer than slot ``n - 1`` (so the last one is the newest)."""
    files: dict[str, bytes] = {}
    newest = max(autos) if autos else 0
    for n in autos:
        files[f"AUTO{n:02d}.DAT"] = make_dat("AUTO", when=(2026, 10, 17, 9 + n, 0, 0), seed=n, log=log)
    for n in story:
        files[f"STORY{n:02d}.DAT"] = make_dat("STORY", when=(2026, 10, 16, 20, n, 0), seed=100 + n, log=log)
    if system:
        files["SYSTEM.DAT"] = make_dat("SYSTEM", seed=200, flags=flags, ring=ring if ring is not None else expected_ring(newest))
    if thumbs:
        for name in [n for n in files if n.startswith(("AUTO", "STORY"))]:
            files[name.replace(".DAT", ".PNG")] = make_png()
    return files


def write_set(folder: Path, files: dict[str, bytes]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return folder


def read_set(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(Path(folder).iterdir()) if p.is_file()}


def snapshot(folder: Path) -> dict[str, str]:
    """Hash of every file under ``folder``, to prove it was not touched."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def diff_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """The maximal runs ``[start, end)`` where two files of the same length differ."""
    assert len(a) == len(b)
    out, start = [], None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y and start is None:
            start = i
        elif x == y and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(a)))
    return out


def differs_only_within(a: bytes, b: bytes, allowed: list[tuple[int, int]]) -> bool:
    return all(any(lo <= s and e <= hi for lo, hi in allowed) for s, e in diff_ranges(a, b))


def sums_of(kind: str) -> list[tuple[int, int]]:
    """The two places a conversion rewrites in every file: the leading checksum and the trailer."""
    return [(0, 4), (end_of(kind) + 4, end_of(kind) + 8)]


def log_area(kind: str) -> list[tuple[int, int]]:
    sb = BASE[kind]
    return [(sb + LOG, sb + LOG + LOG_LEN), (sb + LOG_COUNT, sb + LOG_COUNT + 4)]


def run(capsys, *argv):
    """``(exit code, stdout, stderr)`` of ``saves.main``."""
    code = S.main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def switch_dir(tmp_path):
    """Saves as a Switch writes them: a log full of speaker ids with bit 0x20000000."""
    return write_set(tmp_path / "switch", save_set())


@pytest.fixture
def android_dir(tmp_path):
    """Saves as Android writes them: View Wide on, and its own set of slots."""
    return write_set(tmp_path / "android", save_set(autos=(0, 1, 2, 3), story=(), flags=DEFAULT_FLAGS | VIEW_WIDE, log=0))


# ------------------------------------------------------------------------------------------------ R-1: the format --

@pytest.mark.parametrize("kind", ["SYSTEM", "AUTO", "STORY"])
def test_the_checksum_covers_0x44_up_to_the_trailer(kind):
    """SPEC-011/R-1: the sum starts after the header; changing the date does not change it, changing the payload does."""
    d = make_dat(kind)
    end = end_of(kind)
    assert S.checksum(d, end) == sum(d[0x44:end]) & 0xFFFFFFFF == struct.unpack_from("<I", d, 0)[0]
    assert S.checksum(patched(d, 0x38, struct.pack("<H", 2030)), end) == S.checksum(d, end)
    assert S.checksum(patched(d, 0x100, bytes([d[0x100] ^ 0xFF])), end) != S.checksum(d, end)


@pytest.mark.parametrize("kind", ["SYSTEM", "AUTO", "STORY"])
def test_a_file_stores_the_sum_at_the_start_and_at_the_end(kind):
    """SPEC-011/R-1, R-12: ``refresh`` writes both copies and zeroes the padding word between the payload and the trailer."""
    dirty = patched(patched(make_dat(kind), end_of(kind), b"\xff\xff\xff\xff"), 0, bytes(4))
    d = S.refresh(kind, dirty)
    end = end_of(kind)
    s = sum(d[0x44:end]) & 0xFFFFFFFF
    assert struct.unpack_from("<I", d, 0)[0] == s == struct.unpack_from("<I", d, end + 4)[0]
    assert d[end:end + 4] == bytes(4)


def test_the_header_is_parsed():
    """SPEC-011/R-1"""
    d = make_dat("AUTO", when=(2026, 10, 17, 12, 25, 16))
    h = S.parse_header(d)
    assert (h.magic, h.version, h.size, h.type_id) == (MAGIC, b"ver1.0.0", 0x7110, 3)
    assert h.time == (2026, 10, 17, 12, 25, 16)
    assert S.format_time(h.time) == "2026-10-17 12:25:16"
    assert S.parse_header(make_dat("SYSTEM")).type_id == 0 and S.parse_header(make_dat("STORY")).type_id == 2


# ------------------------------------------------------------------------------------------------ R-2: file names --

@pytest.mark.parametrize("name, expected", [
    ("SYSTEM.DAT", ("SYSTEM", 0, "DAT")), ("system.dat", ("SYSTEM", 0, "DAT")), ("SYSTEM.PNG", ("SYSTEM", 0, "PNG")),
    ("AUTO00.DAT", ("AUTO", 0, "DAT")), ("auto59.png", ("AUTO", 59, "PNG")), ("Story07.Dat", ("STORY", 7, "DAT")),
    ("STORY99.PNG", ("STORY", 99, "PNG")),
])
def test_game_file_names_are_recognised_in_any_case(name, expected):
    """SPEC-011/R-2"""
    assert S.classify(name) == expected


@pytest.mark.parametrize("name", ["AUTO0.DAT", "AUTO000.DAT", "AUTO00.BAK", "SAVE00.DAT", "SYSTEM00.DAT", "autosave.dat",
                                  "ExtraData0", "AUTO00.DAT.bak", ".DAT", ""])
def test_other_names_are_not_saves(name):
    """SPEC-011/R-2"""
    assert S.classify(name) is None


def test_canonical_names():
    """SPEC-011/R-2"""
    assert S.canonical_name("SYSTEM", 0, "DAT") == "SYSTEM.DAT"
    assert S.canonical_name("AUTO", 7, "PNG") == "AUTO07.PNG"
    assert S.canonical_name("STORY", 42, "DAT") == "STORY42.DAT"


# ----------------------------------------------------------------------------------------------------- R-3: verify --

def test_a_clean_set_verifies_without_a_single_problem(switch_dir, capsys):
    """SPEC-011/R-3"""
    files, notes, ignored = S.read_dir(switch_dir)
    assert S.verify_files(files) == [] and notes == [] and ignored == []
    code, out, err = run(capsys, "verify", switch_dir)
    assert code == 0 and "0 errors, 0 warnings" in out and err == ""
    assert "5 .DAT files, 4 .PNG files" in out


@pytest.mark.parametrize("kind", ["SYSTEM", "AUTO", "STORY"])
def test_a_wrong_size_is_an_error(kind):
    """SPEC-011/R-3"""
    good = make_dat(kind)
    for bad in (good[:-1], good + b"\0", b""):
        problems = S.check_dat(kind, bad)
        assert len(problems) == 1 and problems[0][0] == "E" and "size" in problems[0][1]


def test_a_wrong_magic_version_or_header_size_is_an_error():
    """SPEC-011/R-3: these live in the header, which the checksum does not cover, so each is the only problem."""
    good = make_dat("AUTO")
    cases = {
        "magic": patched(good, 4, b"2023(C)OTHER Game".ljust(0x20, b"\0")),
        "version": patched(good, 0x24, b"ver2.0.0".ljust(0xC, b"\0")),
        "size in the header": patched(good, 0x30, struct.pack("<I", 0x7000)),
    }
    for what, bad in cases.items():
        problems = S.check_dat("AUTO", bad)
        assert [lv for lv, _ in problems] == ["E"] and what in problems[0][1], what


def test_a_checksum_that_matches_neither_copy_is_an_error():
    """SPEC-011/R-3"""
    good = make_dat("STORY")
    bad = patched(good, 0x200, bytes([good[0x200] ^ 0x55]))
    problems = S.check_dat("STORY", bad)
    assert len(problems) == 1 and problems[0][0] == "E" and "matches neither" in problems[0][1]


@pytest.mark.parametrize("which", ["start", "trailer"])
def test_either_copy_of_the_checksum_is_enough(which):
    """SPEC-011/R-3: the game accepts the file when one of the two copies is right; ``verify`` only warns about the other."""
    good = make_dat("AUTO")
    offset = 0 if which == "start" else end_of("AUTO") + 4
    bad = patched(good, offset, struct.pack("<I", 0xDEADBEEF))
    problems = S.check_dat("AUTO", bad)
    assert [lv for lv, _ in problems] == ["W"] and "differ" in problems[0][1]
    both = patched(bad, 0 if which == "trailer" else end_of("AUTO") + 4, struct.pack("<I", 0xDEADBEEF))
    assert [lv for lv, _ in S.check_dat("AUTO", both)] == ["E"]


def test_a_wrong_type_padding_or_date_is_only_a_warning():
    """SPEC-011/R-3: the game does not check the type, the padding or the date when it loads."""
    good = make_dat("AUTO")
    assert [lv for lv, _ in S.check_dat("AUTO", patched(good, 0x34, struct.pack("<I", 9)))] == ["W"]
    assert [lv for lv, _ in S.check_dat("AUTO", patched(good, end_of("AUTO"), b"\1\0\0\0"))] == ["W"]
    for date in ((1999, 1, 1, 0, 0, 0), (2026, 13, 1, 0, 0, 0), (2026, 1, 32, 0, 0, 0), (2026, 1, 1, 24, 0, 0),
                 (2026, 1, 1, 0, 60, 0), (2026, 1, 1, 0, 0, 62)):
        problems = S.check_dat("AUTO", patched(good, 0x38, struct.pack("<6H", *date)))
        assert [lv for lv, _ in problems] == ["W"] and "date" in problems[0][1], date
    assert S.check_dat("AUTO", patched(good, 0x38, struct.pack("<6H", 2026, 12, 31, 23, 59, 61))) == []


def test_a_slot_beyond_the_game_range_is_an_error():
    """SPEC-011/R-3: there are 60 autosaves (00-59); the name has two digits, so AUTO60-99 can be written but never exist."""
    d = make_dat("AUTO")
    files = {"AUTO60.DAT": S.Entry.of("AUTO60.DAT", d), "AUTO59.DAT": S.Entry.of("AUTO59.DAT", d)}
    errors = [(n, t) for lv, n, t in S.verify_files(files) if lv == "E"]
    assert len(errors) == 1 and errors[0][0] == "AUTO60.DAT" and "slot out of range (maximum 59)" in errors[0][1]
    story = {"STORY99.DAT": S.Entry.of("STORY99.DAT", make_dat("STORY"))}
    assert not [p for p in S.verify_files(story) if p[0] == "E"]


def test_an_empty_folder_warns_about_what_is_missing():
    """SPEC-011/R-3"""
    problems = S.verify_files({})
    assert [lv for lv, _, _ in problems] == ["W", "W"]
    assert "SYSTEM.DAT" in problems[0][2] and "no save game" in problems[1][2]


def test_verify_target_switch_flags_the_view_wide_bit(tmp_path, capsys):
    """SPEC-011/R-3, R-9: the Android-only option is harmless on Switch, so it is a warning and only for that target."""
    folder = write_set(tmp_path / "s", save_set(flags=DEFAULT_FLAGS | VIEW_WIDE))
    code, out, _ = run(capsys, "verify", folder, "--target", "switch")
    assert code == 0 and "W  SYSTEM.DAT" in out and "View Wide" in out
    code, out, _ = run(capsys, "verify", folder, "--target", "android")
    assert code == 0 and "View Wide" not in out
    code, out, _ = run(capsys, "verify", folder)
    assert code == 0 and "View Wide" not in out


# ------------------------------------------------------------------------------------------------- R-4: thumbnails --

def test_a_valid_thumbnail_is_read():
    """SPEC-011/R-4"""
    assert S.png_info(make_png()) == (240, 136, [])
    assert S.png_info(make_png(16, 8)) == (16, 8, [])


def test_a_thumbnail_written_by_pillow_is_accepted(tmp_path):
    """SPEC-011/R-4"""
    image = pytest.importorskip("PIL.Image")
    path = tmp_path / "t.png"
    image.new("RGBA", (240, 136), (10, 20, 30, 255)).save(path)
    assert S.png_info(path.read_bytes()) == (240, 136, [])


def test_a_damaged_thumbnail_is_an_error():
    """SPEC-011/R-4"""
    good = make_png()
    assert S.png_info(b"GIF89a" + good[6:])[2] == ["bad PNG signature"]
    idat = good.index(b"IDAT")
    assert any("bad CRC" in p for p in S.png_info(patched(good, idat + 6, bytes([good[idat + 6] ^ 0xFF])))[2])
    assert S.png_info(good[:-12])[2] == ["no IEND"]
    assert any("truncated" in p for p in S.png_info(good[:-20])[2])
    assert "no IHDR" in S.png_info(good[:8] + good[8 + 25:])[2]


def test_verify_fails_on_a_damaged_thumbnail(tmp_path, capsys):
    """SPEC-011/R-4, R-14"""
    files = save_set(autos=(0,), story=())
    files["AUTO00.PNG"] = make_png()[:-20]
    folder = write_set(tmp_path / "s", files)
    code, out, _ = run(capsys, "verify", folder)
    assert code == 1 and "E  AUTO00.PNG" in out and "truncated" in out


def test_a_thumbnail_of_another_size_or_without_its_dat_is_a_warning():
    """SPEC-011/R-4"""
    files = {"AUTO00.DAT": S.Entry.of("AUTO00.DAT", make_dat("AUTO")),
             "AUTO00.PNG": S.Entry.of("AUTO00.PNG", make_png(16, 8)),
             "AUTO01.PNG": S.Entry.of("AUTO01.PNG", make_png()),
             "SYSTEM.PNG": S.Entry.of("SYSTEM.PNG", make_png())}
    warnings = {(n, t) for lv, n, t in S.verify_files(files) if lv == "W"}
    assert ("AUTO00.PNG", "thumbnail 16x8 (the game saves 240x136)") in warnings
    assert ("AUTO01.PNG", "thumbnail without its .DAT") in warnings
    assert ("SYSTEM.PNG", "not a file the game uses") in warnings


def test_a_dat_without_a_thumbnail_is_only_information(tmp_path, capsys):
    """SPEC-011/R-4"""
    folder = write_set(tmp_path / "s", save_set(thumbs=False))
    code, out, _ = run(capsys, "verify", folder, "--strict")
    assert code == 0 and "I  AUTO00.DAT" in out and "0 errors, 0 warnings" in out


# --------------------------------------------------------------------------------------------------- R-5: discovery --

def test_a_flat_folder_is_read_as_it_is(switch_dir):
    """SPEC-011/R-5"""
    files, notes, ignored = S.read_dir(switch_dir)
    assert sorted(files) == ["AUTO00.DAT", "AUTO00.PNG", "AUTO01.DAT", "AUTO01.PNG", "AUTO02.DAT", "AUTO02.PNG", "STORY00.DAT",
                             "STORY00.PNG", "SYSTEM.DAT"]
    assert notes == [] and ignored == []
    assert all(e.path == str(switch_dir / n) for n, e in files.items())


def make_ryujinx(root: Path, copies: dict[str, dict[str, bytes]]) -> Path:
    """``<data>/bis/user/save/<saveId>`` with the given copies (``"0"``, ``"1"``) and the files that are not saves."""
    save_id = root / "bis" / "user" / "save" / "0000000000000005"
    for sub, files in copies.items():
        write_set(save_id / sub, files)
    (save_id / "ExtraData0").write_bytes(b"not a save")
    (save_id / "ExtraData1").write_bytes(b"not a save")
    return save_id


def test_ryujinx_save_id_reads_the_committed_copy(tmp_path):
    """SPEC-011/R-5: copy 0 is the committed one; copy 1 is the working copy."""
    old = save_set(autos=(0,), story=())
    new = save_set(autos=(0, 1, 2), story=())
    save_id = make_ryujinx(tmp_path, {"0": new, "1": old})
    files, notes, ignored = S.read_dir(save_id)
    assert "AUTO02.DAT" in files and files["AUTO00.DAT"].path == str(save_id / "0" / "AUTO00.DAT")
    assert notes == [f"input resolved to {save_id / '0'}", "Ryujinx save folder: reading '0' (the committed copy)"]
    assert ignored == []


def test_ryujinx_falls_back_to_the_working_copy(tmp_path):
    """SPEC-011/R-5"""
    save_id = make_ryujinx(tmp_path, {"1": save_set(autos=(0,), story=())})
    files, notes, _ = S.read_dir(save_id)
    assert sorted(files) == ["AUTO00.DAT", "AUTO00.PNG", "SYSTEM.DAT"]
    assert "Ryujinx save folder: reading '1' (the working copy)" in notes


def make_eden(root: Path, files: dict[str, bytes], user: str = "0123456789ABCDEF0123456789ABCDEF") -> Path:
    """``<data>/nand/user/save/0000000000000000/<UserID>/01007D6025CB6000``."""
    return write_set(root / "nand" / "user" / "save" / "0000000000000000" / user / "01007D6025CB6000", files)


def test_eden_folders_are_found_from_any_parent(tmp_path):
    """SPEC-011/R-5"""
    title = make_eden(tmp_path, save_set(autos=(0, 1), story=()))
    for start in (title, title.parent, title.parent.parent, tmp_path / "nand" / "user" / "save", tmp_path / "nand", tmp_path):
        files, notes, _ = S.read_dir(start)
        assert sorted(files) == ["AUTO00.DAT", "AUTO00.PNG", "AUTO01.DAT", "AUTO01.PNG", "SYSTEM.DAT"], start
        assert (start == title) == (notes == []), start
        assert files["SYSTEM.DAT"].path == str(title / "SYSTEM.DAT")


def test_eden_title_folder_is_tried_before_the_others(tmp_path):
    """SPEC-011/R-5: another folder of the same user that sorts first and also holds files like saves must not win."""
    title = make_eden(tmp_path, save_set(autos=(0, 1), story=()))
    decoy = write_set(title.parent / "0000000000000001", {"AUTO05.DAT": make_dat("AUTO", seed=99)})
    files, _, _ = S.read_dir(title.parent)
    assert "AUTO01.DAT" in files and "AUTO05.DAT" not in files
    assert S.find_save_dir(title.parent)[0] == str(title)
    assert S.find_save_dir(decoy.parent)[0] == str(title)


def test_the_search_is_bounded_in_depth(tmp_path):
    """SPEC-011/R-5: pointing at a big folder must not walk the whole disk."""
    deep = tmp_path.joinpath(*[f"d{i}" for i in range(1, S.MAX_SEARCH_DEPTH + 1)])
    write_set(deep, {"AUTO00.DAT": make_dat("AUTO")})
    assert S.find_save_dir(tmp_path)[0] == str(deep)
    too_deep = tmp_path / "other"
    too_deep = too_deep.joinpath(*[f"d{i}" for i in range(1, S.MAX_SEARCH_DEPTH + 2)])
    write_set(too_deep, {"AUTO00.DAT": make_dat("AUTO")})
    assert S.find_save_dir(tmp_path / "other")[0] == str(tmp_path / "other")


def test_a_single_file_can_be_read(tmp_path, capsys):
    """SPEC-011/R-5"""
    path = tmp_path / "auto03.dat"
    path.write_bytes(make_dat("AUTO", log=2))
    files, notes, ignored = S.read_dir(path)
    assert list(files) == ["AUTO03.DAT"] and files["AUTO03.DAT"].slot == 3 and notes == [] and ignored == []
    code, out, _ = run(capsys, "dump", path)
    assert code == 0 and "AUTO03.DAT" in out and "log 2" in out


def test_find_save_dir_gives_a_file_back_as_it_is(tmp_path):
    """SPEC-011/R-5"""
    path = tmp_path / "AUTO00.DAT"
    path.write_bytes(make_dat("AUTO"))
    assert S.find_save_dir(path) == (str(path), [])


def test_a_folder_that_cannot_be_listed_is_skipped(tmp_path, monkeypatch):
    """SPEC-011/R-5: an unreadable folder somewhere below must not stop the search, or end it with a traceback."""
    title = make_eden(tmp_path, save_set(autos=(0,), story=()))
    blocked = title.parent.parent / "0000000000000001"
    blocked.mkdir()
    real_listdir = S.os.listdir

    def listdir(path):
        if str(path) == str(blocked):
            raise PermissionError(13, "Permission denied", str(path))
        return real_listdir(path)

    monkeypatch.setattr(S.os, "listdir", listdir)
    assert S.find_save_dir(title.parent.parent.parent)[0] == str(title)
    assert S.find_save_dir(blocked) == (str(blocked), [])


def test_dump_and_verify_say_what_they_resolved_and_what_they_ignored(tmp_path, capsys):
    """SPEC-011/R-5, R-6"""
    save_id = make_ryujinx(tmp_path, {"0": save_set(autos=(0,), story=())})
    (save_id / "0" / "notes.txt").write_text("mine")
    for command in ("dump", "verify"):
        code, out, _ = run(capsys, command, save_id)
        assert code == 0
        assert f"note: input resolved to {save_id / '0'}" in out and "note: Ryujinx save folder: reading '0'" in out
        assert "ignored (not game saves): notes.txt" in out


def test_a_single_file_must_be_a_save(tmp_path, capsys):
    """SPEC-011/R-5"""
    (tmp_path / "readme.txt").write_text("x")
    with pytest.raises(S.SaveError, match="not a Riviera save file"):
        S.read_dir(tmp_path / "readme.txt")
    code, out, err = run(capsys, "verify", tmp_path / "readme.txt")
    assert code == 1 and out == "" and "is not a Riviera save file" in err


def test_files_that_are_not_saves_are_ignored_not_touched(tmp_path, capsys):
    """SPEC-011/R-2, R-5"""
    folder = write_set(tmp_path / "s", save_set(autos=(0,), story=(), thumbs=False))
    (folder / "notes.txt").write_text("keep me")
    (folder / "AUTO0.DAT").write_bytes(b"x")
    files, _, ignored = S.read_dir(folder)
    assert sorted(ignored) == ["AUTO0.DAT", "notes.txt"] and sorted(files) == ["AUTO00.DAT", "SYSTEM.DAT"]
    code, out, _ = run(capsys, "verify", folder)
    assert code == 0 and "ignored (not game saves): AUTO0.DAT, notes.txt" in out


def test_lower_case_names_are_read_under_their_canonical_name(tmp_path):
    """SPEC-011/R-2, R-5"""
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / "auto00.dat").write_bytes(make_dat("AUTO"))
    (folder / "System.Dat").write_bytes(make_dat("SYSTEM"))
    files, _, ignored = S.read_dir(folder)
    assert sorted(files) == ["AUTO00.DAT", "SYSTEM.DAT"] and ignored == []
    assert files["AUTO00.DAT"].path == str(folder / "auto00.dat")


def test_the_same_save_under_two_spellings_is_read_once(tmp_path):
    """SPEC-011/R-2, R-5"""
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / "AUTO00.DAT").write_bytes(make_dat("AUTO"))
    (folder / "auto00.dat").write_bytes(make_dat("AUTO", seed=5))
    if len(list(folder.iterdir())) < 2:
        pytest.skip("this file system ignores the case of file names")
    files, notes, _ = S.read_dir(folder)
    assert list(files) == ["AUTO00.DAT"] and files["AUTO00.DAT"].path == str(folder / "AUTO00.DAT")
    assert notes == ["'AUTO00.DAT' and 'auto00.dat' are the same save; the first one is used"]


def test_a_path_that_does_not_exist_is_an_error(tmp_path, capsys):
    """SPEC-011/R-5, R-14"""
    with pytest.raises(S.SaveError, match="no such folder"):
        S.read_dir(tmp_path / "nope")
    for command in ("dump", "verify"):
        code, out, err = run(capsys, command, tmp_path / "nope")
        assert code == 1 and out == "" and "error: no such folder" in err


# -------------------------------------------------------------------------------------------------------- R-6: dump --

def test_dump_describes_every_slot(switch_dir, capsys):
    """SPEC-011/R-6"""
    code, out, err = run(capsys, "dump", switch_dir)
    assert code == 0 and err == ""
    line = next(ln for ln in out.splitlines() if ln.startswith("AUTO01.DAT"))
    for part in ("28944 B", "2026-10-17 10:00:00", "area 1-1", "normal/standard", "time 001:02:03", "score 2200", "party [0, 5]",
                 "log 4", "(checksum OK)"):
        assert part in line, part
    assert next(ln for ln in out.splitlines() if ln.startswith("STORY00.DAT")).count("5176") == 0
    assert "AUTO00.PNG" in out and "PNG 240x136" in out
    assert out.rstrip().endswith("newest autosave by date: AUTO02")


def test_dump_describes_the_system_file(tmp_path, capsys):
    """SPEC-011/R-6"""
    folder = write_set(tmp_path / "s", save_set(flags=CONTROLLER_B | VIEW_WIDE | 1))
    code, out, _ = run(capsys, "dump", folder)
    assert code == 0
    assert "SYSTEM.DAT       5176 B" in out
    assert "config 0x00800101" in out and "text speed 4" in out and "BGM/SE/voice (60, 70, 80)" in out
    assert "options on: LearnTeam, ControllerB, ViewWide (Android only)" in out
    assert "game cleared: False  last save: 2" in out
    assert "autosave rotation (the first one is the newest): [2, 1, 0, 59, 58, 57, 56, 55] ..." in out


def test_dump_json_is_complete_and_parseable(switch_dir, capsys):
    """SPEC-011/R-6"""
    code, out, _ = run(capsys, "dump", switch_dir, "--json")
    assert code == 0
    data = json.loads(out)
    assert data["newest_autosave"] == 2 and data["notes"] == [] and data["ignored"] == []
    names = [f["file"] for f in data["files"]]
    assert names[0] == "SYSTEM.DAT" and names[1:] == sorted(names[1:])
    by_name = {f["file"]: f for f in data["files"]}
    slot = by_name["AUTO02.DAT"]["slot"]
    assert (slot["play_time"], slot["area"], slot["stage"], slot["difficulty"], slot["mode"], slot["score"], slot["party"],
            slot["log_messages"]) == ("001:02:03", 1, 1, "normal", "standard", 2200, [0, 5], 4)
    assert by_name["AUTO02.DAT"]["date"] == "2026-10-17 11:00:00" and by_name["AUTO02.DAT"]["problems"] == []
    system = by_name["SYSTEM.DAT"]["system"]
    assert system["config_flags"] == "0x002fa907" and system["config_bits"]["ControllerB"] is True
    assert system["autosave_rotation"] == expected_ring(2)
    assert (by_name["AUTO00.PNG"]["width"], by_name["AUTO00.PNG"]["height"]) == (240, 136)


def test_dump_names_unknown_levels_and_modes_by_number(tmp_path, capsys):
    """SPEC-011/R-6"""
    folder = write_set(tmp_path / "s", {"AUTO00.DAT": make_dat("AUTO", level=7, mode=9)})
    code, out, _ = run(capsys, "dump", folder)
    assert code == 0 and "7/9" in out
    assert S.decode_slot("AUTO", make_dat("AUTO", level=0, mode=3))["difficulty"] == "easy"
    assert S.decode_slot("AUTO", make_dat("AUTO", level=3, mode=3))["mode"] == "highlevel"


def test_the_item_count_follows_the_games_bit_maps():
    """SPEC-011/R-6: items obtained are counted in two bit maps of SysSramSys; some indices of the first one are not items."""
    d = bytearray(make_dat("SYSTEM"))
    d[SYS + 0x48:SYS + 0x48 + 50] = bytes(50)
    assert S.item_count(d) == 0

    def set_bit(base: int, idx: int) -> None:
        d[SYS + base + (idx >> 3)] |= 1 << (idx & 7)

    for idx in (0, 10, 154, 3, 9):                 # 0, 10 and 154 count; 3 (inside 1-7) and 9 are not items
        set_bit(0x48, idx)
    for idx in (5, 5 + 0x50, 70 + 2 * 0x50):       # i = 5 (set in two of the three maps: once) and i = 70
        set_bit(0x5C, idx)
    assert S.item_count(d) == 5
    assert S.decode_system(seal(d, "SYSTEM"))["items"] == 5


def test_unnamed_option_bits_are_shown_by_number():
    """SPEC-011/R-6"""
    options = S.decode_system(make_dat("SYSTEM", flags=1 << 6 | 1 << 7 | CONTROLLER_B))["config_bits"]
    assert options == {"bit6": True, "bit7": True, "ControllerB": True}


def test_dump_verbose_shows_the_fields_that_hold_addresses(tmp_path, capsys):
    """SPEC-011/R-6: the addresses depend on the platform, which tells where a save was made."""
    d = bytearray(make_dat("AUTO"))
    g = BASE["AUTO"] + 0x18
    struct.pack_into("<Q", d, g + 0x10, 0x08123456)               # a Switch address
    struct.pack_into("<Q", d, g + 0x18, 0x6E18123456)             # an Android address
    struct.pack_into("<Q", d, g + 0x20, 0)
    folder = write_set(tmp_path / "s", {"AUTO00.DAT": seal(d, "AUTO")})
    code, plain, _ = run(capsys, "dump", folder)
    assert code == 0 and "gSys+0x10" not in plain
    code, out, _ = run(capsys, "dump", folder, "-v")
    assert code == 0
    rows = {ln.split()[0]: ln for ln in out.splitlines() if ln.strip().startswith(("gSys+", "member"))}
    assert len(rows) == 13 and rows["gSys+0x10"].rstrip().endswith("Switch") and rows["gSys+0x18"].rstrip().endswith("Android")
    assert rows["gSys+0x20"].rstrip().endswith("null") and "0x8123456" in rows["gSys+0x10"]
    code, out, _ = run(capsys, "dump", folder, "--verbose", "--json")
    assert [p["platform"] for p in json.loads(out)["files"][0]["pointers"]][:3] == ["Switch", "Android", "null"]


@pytest.mark.parametrize("value, platform", [(0, "null"), (0x08000000, "Switch"), (0x0FFFFFFF, "Switch"), (0x10000000, "?"),
                                              (0x6000000000, "Android"), (0x7FFFFFFFFF, "Android"), (0x8000000000, "?"), (1, "?")])
def test_platform_guess(value, platform):
    """SPEC-011/R-6"""
    assert S.platform_guess(value) == platform


def test_dump_reports_damaged_files_and_still_succeeds(tmp_path, capsys):
    """SPEC-011/R-6: dump is for looking; it is `verify` that fails."""
    files = save_set(autos=(0, 1), story=(0,))
    files["AUTO01.DAT"] = patched(files["AUTO01.DAT"], 0x200, b"\x00\x01\x02")          # breaks the checksum
    files["AUTO00.DAT"] = files["AUTO00.DAT"][:-5]                                      # wrong size
    files["AUTO00.PNG"] = b"not a png"
    files["STORY00.DAT"] = patched(files["STORY00.DAT"], 4, b"2023(C)OTHER")             # not a Riviera save
    folder = write_set(tmp_path / "s", files)
    code, out, _ = run(capsys, "dump", folder)
    assert code == 0
    story = next(ln for ln in out.splitlines() if ln.startswith("STORY00.DAT"))
    assert "<<< E: magic" in story and "area" not in story                                # nothing is decoded from it
    assert any(ln.startswith("AUTO00.DAT") and "<<< E: size 28939 (expected 28944)" in ln for ln in out.splitlines())
    assert any(ln.startswith("AUTO01.DAT") and "<<< E: checksum" in ln for ln in out.splitlines())
    assert any(ln.startswith("AUTO00.PNG") and "bad PNG signature" in ln for ln in out.splitlines())
    code, out, _ = run(capsys, "dump", folder, "--json")
    assert code == 0 and json.loads(out)["newest_autosave"] == 1


# --------------------------------------------------------------------------------------- R-7: a new folder, always --

COMMANDS = ["switch2android", "android2switch", "switch2switch"]


@pytest.mark.parametrize("command", COMMANDS)
def test_a_conversion_never_modifies_its_input(command, tmp_path, capsys):
    """SPEC-011/R-7"""
    src = write_set(tmp_path / "in", save_set(flags=DEFAULT_FLAGS | VIEW_WIDE, log=6))
    dest = write_set(tmp_path / "dest", {"SYSTEM.DAT": make_dat("SYSTEM", seed=7, flags=VIEW_WIDE)})
    before = snapshot(tmp_path)
    code, out, _ = run(capsys, command, src, tmp_path / "out", "--dest-system", dest / "SYSTEM.DAT", "--keep-dest-config")
    assert code == 0
    after = snapshot(tmp_path)
    assert {k: v for k, v in after.items() if not k.startswith("out")} == before
    assert any(k.startswith("out") for k in after)


@pytest.mark.parametrize("command", COMMANDS)
def test_clean_saves_come_out_byte_for_byte_identical(command, tmp_path, capsys):
    """SPEC-011/R-7: no log, no View Wide, a consistent rotation table, valid sums: there is nothing to normalise."""
    files = save_set(log=0)
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, command, src, tmp_path / "out")
    assert code == 0 and read_set(tmp_path / "out") == files
    assert "change:" not in out


def test_the_report_names_the_platforms_and_how_to_install(switch_dir, android_dir, tmp_path, capsys):
    """SPEC-011/R-7"""
    _, out, _ = run(capsys, "switch2android", switch_dir, tmp_path / "a")
    assert f"switch -> android: 9 files written to {tmp_path / 'a'} (source: {switch_dir})" in out
    assert "newest autosave: AUTO02" in out and "replacing the WHOLE save folder" in out
    _, out, _ = run(capsys, "android2switch", android_dir, tmp_path / "b")
    assert f"android -> switch: {len(read_set(android_dir))} files written" in out and len(read_set(android_dir)) == 9
    _, out, _ = run(capsys, "switch2switch", switch_dir, tmp_path / "c")
    assert "switch -> switch: 9 files written" in out


@pytest.mark.parametrize("where", ["same", "inside", "around"])
def test_the_output_cannot_be_the_input_inside_it_or_around_it(where, switch_dir, tmp_path, capsys):
    """SPEC-011/R-7"""
    dst = {"same": switch_dir, "inside": switch_dir / "out", "around": switch_dir.parent}[where]
    before = snapshot(tmp_path)
    code, out, err = run(capsys, "switch2android", switch_dir, dst, "--force")
    assert code == 1 and "new folder" in err and snapshot(tmp_path) == before


def test_the_output_is_compared_by_identity_not_by_spelling(switch_dir, tmp_path, capsys):
    """SPEC-011/R-7: where the file system ignores case ``SWITCH`` is the input folder ``switch``, and --force must not touch it."""
    alias = switch_dir.parent / switch_dir.name.upper()
    if not alias.exists():
        pytest.skip("this file system is case sensitive")
    before = snapshot(tmp_path)
    for dst in (alias, alias / "out"):
        code, _, err = run(capsys, "switch2android", switch_dir, dst, "--force")
        assert code == 1 and "new folder" in err and snapshot(tmp_path) == before
    link = tmp_path / "link"
    try:
        link.symlink_to(switch_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    code, _, err = run(capsys, "switch2android", switch_dir, link, "--force")
    assert code == 1 and "new folder" in err and snapshot(tmp_path) == before


def test_the_output_cannot_be_the_ryujinx_folder_around_the_resolved_input(tmp_path, capsys):
    """SPEC-011/R-5, R-7: the input is resolved to ``<saveId>/0``, so ``<saveId>`` itself is around it."""
    save_id = make_ryujinx(tmp_path, {"0": save_set(), "1": save_set()})
    before = snapshot(tmp_path)
    code, _, err = run(capsys, "switch2switch", save_id, save_id, "--force")
    assert code == 1 and "new folder" in err and snapshot(tmp_path) == before


def test_a_conversion_can_read_the_ryujinx_folder_and_write_to_its_other_copy(tmp_path, capsys):
    """SPEC-011/R-5, R-7: ``<saveId>/0`` is the input, ``<saveId>/1`` the output, which is fine with --force."""
    save_id = make_ryujinx(tmp_path, {"0": save_set(log=0), "1": save_set(autos=(0,), story=(), log=0)})
    code, out, _ = run(capsys, "switch2switch", save_id, save_id / "1", "--force")
    assert code == 0 and "input resolved to" in out
    assert sorted(read_set(save_id / "1")) == sorted(read_set(save_id / "0"))


def test_an_output_that_is_not_empty_needs_force(switch_dir, tmp_path, capsys):
    """SPEC-011/R-7: --force removes only what looks like a save; any other file stays."""
    out_dir = write_set(tmp_path / "out", {"AUTO07.DAT": b"stale", "AUTO07.PNG": b"stale", "notes.txt": b"mine"})
    before = snapshot(out_dir)
    code, out, err = run(capsys, "switch2android", switch_dir, out_dir)
    assert code == 1 and "already exists and is not empty (use --force" in err and snapshot(out_dir) == before
    code, out, err = run(capsys, "switch2android", switch_dir, out_dir, "--force")
    assert code == 0
    left = read_set(out_dir)
    assert "AUTO07.DAT" not in left and "AUTO07.PNG" not in left and left["notes.txt"] == b"mine"
    assert {"SYSTEM.DAT", "AUTO00.DAT", "AUTO02.PNG", "STORY00.DAT"} <= set(left)


def test_an_existing_empty_output_folder_is_fine(switch_dir, tmp_path, capsys):
    """SPEC-011/R-7"""
    (tmp_path / "out").mkdir()
    code, _, _ = run(capsys, "switch2android", switch_dir, tmp_path / "out")
    assert code == 0 and "SYSTEM.DAT" in read_set(tmp_path / "out")
    code, _, _ = run(capsys, "switch2android", switch_dir, tmp_path / "new" / "deep" / "out")
    assert code == 0 and "SYSTEM.DAT" in read_set(tmp_path / "new" / "deep" / "out")


def test_thumbnails_are_copied_as_they_are_and_orphans_are_dropped(tmp_path, capsys):
    """SPEC-011/R-7"""
    files = save_set(autos=(0,), story=())
    files["AUTO05.PNG"] = make_png()                       # its AUTO05.DAT does not exist
    src = write_set(tmp_path / "in", files)
    code, _, _ = run(capsys, "switch2android", src, tmp_path / "out")
    out = read_set(tmp_path / "out")
    assert code == 0 and out["AUTO00.PNG"] == make_png() and "AUTO05.PNG" not in out


def test_a_conversion_leaves_other_files_behind_and_says_so(tmp_path, capsys):
    """SPEC-011/R-2, R-7"""
    src = write_set(tmp_path / "in", {**save_set(autos=(0,), story=(), log=0), "notes.txt": b"mine", "ExtraData0": b"x"})
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out")
    assert code == 0 and "ignored: ExtraData0, notes.txt" in out
    assert "notes.txt" not in read_set(tmp_path / "out") and "ExtraData0" not in read_set(tmp_path / "out")


def test_a_converted_folder_converts_to_itself(tmp_path, capsys):
    """SPEC-011/R-7, R-12: the output is already normalised, so converting it again gives the same bytes."""
    src = write_set(tmp_path / "in", save_set(flags=DEFAULT_FLAGS | VIEW_WIDE, log=5, ring=list(range(60))))
    assert run(capsys, "android2switch", src, tmp_path / "once")[0] == 0
    for command in COMMANDS:
        assert run(capsys, command, tmp_path / "once", tmp_path / ("again_" + command))[0] == 0
        assert read_set(tmp_path / ("again_" + command)) == read_set(tmp_path / "once")


def test_convert_accepts_path_objects(switch_dir, tmp_path, capsys):
    """SPEC-011/R-7: ``convert`` is usable as a library function."""
    assert S.convert(switch_dir, tmp_path / "out", source="switch", target="android", only_newest_auto=True) == 0
    assert "AUTO02.DAT" in read_set(tmp_path / "out")
    assert "switch -> android" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------------- R-8: the log --

@pytest.mark.parametrize("command", COMMANDS)
def test_the_message_log_is_emptied_and_nothing_else_changes(command, tmp_path, capsys):
    """SPEC-011/R-8: Android crashes opening the log of a Switch save, so every conversion empties it."""
    files = save_set(log=5)
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, command, src, tmp_path / "out")
    assert code == 0
    result = read_set(tmp_path / "out")
    for name in ("AUTO00.DAT", "AUTO01.DAT", "AUTO02.DAT", "STORY00.DAT"):
        kind = name[:-6] if name.startswith("AUTO") else "STORY"
        sb = BASE[kind]
        d = result[name]
        assert struct.unpack_from("<I", d, sb + LOG_COUNT)[0] == 0
        assert d[sb + LOG:sb + LOG + LOG_LEN] == bytes(LOG_LEN)
        assert S.check_dat(kind, d) == []
        assert differs_only_within(files[name], d, sums_of(kind) + log_area(kind)), name
        assert f"change: {name}: message log (LOG) emptied (5 entries)" in out
    assert result["SYSTEM.DAT"] == files["SYSTEM.DAT"]
    assert all(result[n] == files[n] for n in files if n.endswith(".PNG"))


def test_keep_log_keeps_the_log(tmp_path, capsys):
    """SPEC-011/R-8"""
    files = save_set(log=5)
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out", "--keep-log")
    assert code == 0 and read_set(tmp_path / "out") == files and "LOG" not in out


def test_clearing_the_log_zeroes_the_whole_area_and_the_count():
    """SPEC-011/R-8"""
    for kind in ("AUTO", "STORY"):
        d = make_dat(kind, log=9)
        assert S.log_entries(kind, d) == 9
        cleared = S.clear_log(kind, d)
        assert S.log_entries(kind, cleared) == 0 and cleared[BASE[kind] + LOG:BASE[kind] + LOG + LOG_LEN] == bytes(LOG_LEN)
        assert differs_only_within(d, cleared, log_area(kind))


# ------------------------------------------------------------------------------------------------- R-9: the config --

def read_flags(d: bytes) -> int:
    return struct.unpack_from("<I", d, CFG)[0]


def system_changes_only(a: bytes, b: bytes, extra=()) -> bool:
    """The only parts of SYSTEM.DAT a conversion may change: the option word, the rotation table, the sums (and ``extra``)."""
    return differs_only_within(a, b, [(CFG, CFG + 4), (RING, RING + 60), *sums_of("SYSTEM"), *extra])


@pytest.mark.parametrize("command", ["android2switch", "switch2switch"])
def test_view_wide_is_cleared_when_the_destination_is_a_switch(command, android_dir, tmp_path, capsys):
    """SPEC-011/R-9"""
    original = read_set(android_dir)["SYSTEM.DAT"]
    assert read_flags(original) == DEFAULT_FLAGS | VIEW_WIDE
    code, out, _ = run(capsys, command, android_dir, tmp_path / "out")
    assert code == 0
    system = read_set(tmp_path / "out")["SYSTEM.DAT"]
    assert read_flags(system) == DEFAULT_FLAGS and system_changes_only(original, system)
    assert "change: SYSTEM.DAT: config 0x00afa907 -> 0x002fa907 (bit 23, View Wide, exists only on Android)" in out


def test_view_wide_is_cleared_for_android_too_unless_the_destination_has_it(android_dir, tmp_path, capsys):
    """SPEC-011/R-9"""
    code, _, _ = run(capsys, "switch2android", android_dir, tmp_path / "plain")
    assert code == 0 and read_flags(read_set(tmp_path / "plain")["SYSTEM.DAT"]) == DEFAULT_FLAGS
    on = write_set(tmp_path / "dest_on", {"SYSTEM.DAT": make_dat("SYSTEM", seed=3, flags=VIEW_WIDE | 1)})
    off = write_set(tmp_path / "dest_off", {"SYSTEM.DAT": make_dat("SYSTEM", seed=3, flags=1)})
    code, _, _ = run(capsys, "switch2android", android_dir, tmp_path / "kept", "--dest-system", on / "SYSTEM.DAT")
    assert code == 0 and read_flags(read_set(tmp_path / "kept")["SYSTEM.DAT"]) == DEFAULT_FLAGS | VIEW_WIDE
    code, _, _ = run(capsys, "switch2android", android_dir, tmp_path / "none", "--dest-system", off / "SYSTEM.DAT")
    assert code == 0 and read_flags(read_set(tmp_path / "none")["SYSTEM.DAT"]) == DEFAULT_FLAGS


def test_view_wide_from_the_destination_never_reaches_a_switch(android_dir, tmp_path, capsys):
    """SPEC-011/R-9"""
    dest = write_set(tmp_path / "dest", {"SYSTEM.DAT": make_dat("SYSTEM", seed=3, flags=VIEW_WIDE)})
    code, _, _ = run(capsys, "android2switch", android_dir, tmp_path / "out", "--dest-system", dest / "SYSTEM.DAT")
    assert code == 0 and read_flags(read_set(tmp_path / "out")["SYSTEM.DAT"]) & VIEW_WIDE == 0


def test_the_configuration_travels_with_the_save_controller_b_included(tmp_path, capsys):
    """SPEC-011/R-9: with Controller B on, B confirms; without --keep-dest-config the source's choice wins."""
    src = write_set(tmp_path / "in", save_set(flags=DEFAULT_FLAGS | CONTROLLER_B))
    dest = write_set(tmp_path / "dest", {"SYSTEM.DAT": make_dat("SYSTEM", seed=3, flags=DEFAULT_FLAGS & ~CONTROLLER_B)})
    code, _, _ = run(capsys, "switch2switch", src, tmp_path / "plain", "--dest-system", dest / "SYSTEM.DAT")
    assert code == 0 and read_flags(read_set(tmp_path / "plain")["SYSTEM.DAT"]) & CONTROLLER_B
    code, out, _ = run(capsys, "switch2switch", src, tmp_path / "kept", "--dest-system", dest / "SYSTEM.DAT", "--keep-dest-config")
    assert code == 0 and read_flags(read_set(tmp_path / "kept")["SYSTEM.DAT"]) & CONTROLLER_B == 0
    assert "change: SYSTEM.DAT: ConfigWork (options, volumes, menu state) taken from the destination" in out


@pytest.mark.parametrize("command, view_wide_expected",
                         [("switch2android", True), ("android2switch", False), ("switch2switch", False)])
def test_keep_dest_config_takes_the_whole_configuration_of_the_destination(command, view_wide_expected, android_dir, tmp_path,
                                                                           capsys):
    """SPEC-011/R-9: only the progress travels; the destination's options and volumes stay (View Wide as the platform allows)."""
    dest_bytes = make_dat("SYSTEM", seed=3, flags=0x00800102, text_speed=1, volumes=(5, 6, 7))
    dest = write_set(tmp_path / "dest", {"SYSTEM.DAT": dest_bytes})
    src_system = read_set(android_dir)["SYSTEM.DAT"]
    code, _, _ = run(capsys, command, android_dir, tmp_path / "out", "--dest-system", dest / "SYSTEM.DAT", "--keep-dest-config")
    assert code == 0
    out = read_set(tmp_path / "out")["SYSTEM.DAT"]
    assert read_flags(out) == (0x00800102 if view_wide_expected else 0x00000102)
    assert out[CFG + 4:CFG + CFG_LEN] == dest_bytes[CFG + 4:CFG + CFG_LEN]        # options, volumes, the rest of ConfigWork
    assert out[SYS:CFG] == src_system[SYS:CFG]                                    # the progress comes from the source
    assert out[0x4:0x48] == src_system[0x4:0x48]


def test_keep_dest_config_needs_dest_system(switch_dir, tmp_path, capsys):
    """SPEC-011/R-9: otherwise it would silently do nothing, and the player would think the configuration was kept."""
    code, out, err = run(capsys, "switch2android", switch_dir, tmp_path / "out", "--keep-dest-config")
    assert code == 1 and "--keep-dest-config needs --dest-system" in err and not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind_of_damage", ["checksum", "size", "missing"])
def test_an_invalid_dest_system_aborts_without_writing(kind_of_damage, switch_dir, tmp_path, capsys):
    """SPEC-011/R-9"""
    good = make_dat("SYSTEM", seed=3)
    dest = tmp_path / "SYSTEM.DAT"
    if kind_of_damage == "checksum":
        dest.write_bytes(patched(good, 0x100, b"\xAA\xBB"))
    elif kind_of_damage == "size":
        dest.write_bytes(good[:100])
    code, out, err = run(capsys, "switch2android", switch_dir, tmp_path / "out", "--dest-system", dest, "--keep-dest-config")
    assert code == 1 and err.startswith("error: ") and "Traceback" not in err and not (tmp_path / "out").exists()
    if kind_of_damage != "missing":
        assert "--dest-system does not validate" in err


# --------------------------------------------------------------------------------------- R-10: the rotation table --

def autosaves_dated(*dates) -> dict[str, bytes]:
    """AUTO saves with the given ``(slot, hour, minute)`` header dates and a stale rotation table in SYSTEM.DAT."""
    files = {f"AUTO{slot:02d}.DAT": make_dat("AUTO", when=(2026, 10, 17, hour, minute, 0), seed=slot)
             for slot, hour, minute in dates}
    files["SYSTEM.DAT"] = make_dat("SYSTEM", ring=list(range(60)))
    return files


def test_the_rotation_table_is_rebuilt_from_the_dates(tmp_path, capsys):
    """SPEC-011/R-10: newest first (AUTO02 here, by its date and not by its number), then downwards, wrapping from 0 to 59."""
    files = autosaves_dated((0, 9, 0), (1, 10, 0), (2, 15, 0), (3, 11, 0))
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out")
    assert code == 0
    system = read_set(tmp_path / "out")["SYSTEM.DAT"]
    ring = list(system[RING:RING + 60])
    assert ring == [2, 1, 0] + list(range(59, 2, -1)) and sorted(ring) == list(range(60))
    assert "change: SYSTEM.DAT: rotation table -> AUTO02 first" in out and "newest autosave: AUTO02" in out
    assert S.checksum(system, end_of("SYSTEM")) == struct.unpack_from("<I", system, 0)[0]
    assert system_changes_only(files["SYSTEM.DAT"], system)


def test_the_rotation_table_wraps_below_zero(tmp_path, capsys):
    """SPEC-011/R-10"""
    src = write_set(tmp_path / "in", autosaves_dated((5, 9, 0), (7, 12, 0)))
    run(capsys, "switch2switch", src, tmp_path / "out")
    ring = list(read_set(tmp_path / "out")["SYSTEM.DAT"][RING:RING + 60])
    assert ring[:9] == [7, 6, 5, 4, 3, 2, 1, 0, 59] and ring[-1] == 8


def test_on_a_tie_the_lowest_slot_is_the_newest(tmp_path, capsys):
    """SPEC-011/R-10: like the game, which keeps the first one it meets."""
    files = autosaves_dated((1, 12, 0), (3, 12, 0), (2, 8, 0))
    assert S.newest_auto({n: S.Entry.of(n, d) for n, d in files.items() if n.startswith("AUTO")}) == 1
    src = write_set(tmp_path / "in", files)
    run(capsys, "switch2switch", src, tmp_path / "out")
    assert read_set(tmp_path / "out")["SYSTEM.DAT"][RING] == 1


def test_the_date_of_the_header_decides_not_the_slot_number():
    """SPEC-011/R-10: seconds count, and so do the day and the year."""
    entries = {
        "AUTO00.DAT": S.Entry.of("AUTO00.DAT", make_dat("AUTO", when=(2026, 10, 17, 12, 0, 1))),
        "AUTO01.DAT": S.Entry.of("AUTO01.DAT", make_dat("AUTO", when=(2026, 10, 17, 12, 0, 0))),
        "AUTO02.DAT": S.Entry.of("AUTO02.DAT", make_dat("AUTO", when=(2026, 10, 16, 23, 59, 59))),
        "AUTO03.DAT": S.Entry.of("AUTO03.DAT", make_dat("AUTO", when=(2025, 12, 31, 23, 59, 59))),
    }
    assert S.newest_auto(entries) == 0
    del entries["AUTO00.DAT"]
    assert S.newest_auto(entries) == 1
    assert S.newest_auto({}) is None
    assert S.ring_for({}) is None
    assert S.ring_for(entries) == expected_ring(1)


def test_a_stale_rotation_table_is_information_for_verify(tmp_path, capsys):
    """SPEC-011/R-10: the game rebuilds it on load, so this never fails a check, not even --strict."""
    folder = write_set(tmp_path / "s", autosaves_dated((0, 9, 0), (1, 10, 0)))
    code, out, _ = run(capsys, "verify", folder, "--strict")
    assert "I  SYSTEM.DAT" in out and "rotation table does not match" in out
    assert code == 0 and "0 errors" in out
    ok = write_set(tmp_path / "ok", {**autosaves_dated((0, 9, 0), (1, 10, 0)),
                                     "SYSTEM.DAT": make_dat("SYSTEM", ring=expected_ring(1))})
    _, out, _ = run(capsys, "verify", ok)
    assert "rotation table" not in out


def test_without_autosaves_the_rotation_table_is_left_alone(tmp_path, capsys):
    """SPEC-011/R-10"""
    files = save_set(autos=(), story=(0,), thumbs=False, ring=list(range(60)))
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out", "--keep-log")
    assert code == 0 and read_set(tmp_path / "out") == files and "rotation table" not in out
    assert "newest autosave" not in out


def test_a_conversion_without_system_dat_says_so(tmp_path, capsys):
    """SPEC-011/R-10: the destination keeps its own SYSTEM.DAT, and its rotation table is rebuilt by the game."""
    src = write_set(tmp_path / "in", save_set(system=False))
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out")
    assert code == 0 and "warning: the output has no SYSTEM.DAT" in out
    assert "SYSTEM.DAT" not in read_set(tmp_path / "out")


# -------------------------------------------------------------------------------------------------- R-11: selection --

def test_only_the_newest_autosave_with_its_thumbnail(tmp_path, capsys):
    """SPEC-011/R-10, R-11"""
    src = write_set(tmp_path / "in", save_set(autos=(0, 1, 2, 3), log=0))
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out", "--only-newest-auto")
    assert code == 0
    left = sorted(read_set(tmp_path / "out"))
    assert left == ["AUTO03.DAT", "AUTO03.PNG", "STORY00.DAT", "STORY00.PNG", "SYSTEM.DAT"]
    assert list(read_set(tmp_path / "out")["SYSTEM.DAT"][RING:RING + 3]) == [3, 2, 1] and "switch -> android: 5 files" in out


def test_the_newest_autosave_is_chosen_among_the_valid_ones(tmp_path, capsys):
    """SPEC-011/R-11: a broken newest save must not make the whole conversion lose its autosave."""
    files = save_set(autos=(0, 1, 2), story=(), log=0)
    files["AUTO02.DAT"] = patched(files["AUTO02.DAT"], 0x300, b"\xff\xfe")
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out", "--only-newest-auto", "--skip-invalid")
    assert code == 0 and sorted(read_set(tmp_path / "out")) == ["AUTO01.DAT", "AUTO01.PNG", "SYSTEM.DAT"]


def test_no_story_leaves_the_manual_saves_out(tmp_path, capsys):
    """SPEC-011/R-11"""
    src = write_set(tmp_path / "in", save_set(autos=(0,), story=(0, 1, 2), log=0))
    code, _, _ = run(capsys, "switch2android", src, tmp_path / "out", "--no-story")
    assert code == 0 and sorted(read_set(tmp_path / "out")) == ["AUTO00.DAT", "AUTO00.PNG", "SYSTEM.DAT"]


def test_options_combine(tmp_path, capsys):
    """SPEC-011/R-11"""
    src = write_set(tmp_path / "in", save_set(autos=(0, 1, 2), story=(0,), log=0))
    code, _, _ = run(capsys, "switch2android", src, tmp_path / "out", "--no-story", "--only-newest-auto")
    assert code == 0 and sorted(read_set(tmp_path / "out")) == ["AUTO02.DAT", "AUTO02.PNG", "SYSTEM.DAT"]


@pytest.mark.parametrize("damage, text", [("checksum", "checksum"), ("size", "size"), ("slot", "slot out of range"),
                                          ("png", "invalid PNG")])
def test_a_file_that_does_not_validate_aborts_the_conversion(damage, text, tmp_path, capsys):
    """SPEC-011/R-11: nothing is written, and the output folder is not even created."""
    files = save_set(autos=(0, 1), story=())
    if damage == "checksum":
        files["AUTO01.DAT"] = patched(files["AUTO01.DAT"], 0x200, b"\x01\x02\x03")
    elif damage == "size":
        files["AUTO01.DAT"] = files["AUTO01.DAT"][:-1]
    elif damage == "slot":
        files["AUTO60.DAT"] = make_dat("AUTO")
    else:
        files["AUTO01.PNG"] = files["AUTO01.PNG"][:-20]
    src = write_set(tmp_path / "in", files)
    code, out, err = run(capsys, "switch2android", src, tmp_path / "out")
    assert code == 1 and "does not validate" in err and not (tmp_path / "out").exists()
    assert "ERROR  " in out and text in out


@pytest.mark.parametrize("damage", ["checksum", "size", "png"])
def test_skip_invalid_leaves_them_out_and_says_so(damage, tmp_path, capsys):
    """SPEC-011/R-7, R-11: a thumbnail whose .DAT was left out goes too."""
    files = save_set(autos=(0, 1), story=(), log=0)
    if damage == "checksum":
        files["AUTO01.DAT"] = patched(files["AUTO01.DAT"], 0x200, b"\x01\x02\x03")
    elif damage == "size":
        files["AUTO01.DAT"] = files["AUTO01.DAT"][:-1]
    else:
        files["AUTO01.PNG"] = b"not a png"
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out", "--skip-invalid")
    assert code == 0 and "skipped  AUTO01." in out
    left = sorted(read_set(tmp_path / "out"))
    if damage == "png":
        assert left == ["AUTO00.DAT", "AUTO00.PNG", "AUTO01.DAT", "SYSTEM.DAT"]
    else:
        assert left == ["AUTO00.DAT", "AUTO00.PNG", "SYSTEM.DAT"]


# ------------------------------------------------------------------------------------------------ R-12: the sums --

def test_the_sums_are_recalculated_on_output(tmp_path, capsys):
    """SPEC-011/R-12: an input whose two copies differ (the game accepts it) comes out with both right."""
    files = save_set(autos=(0,), story=(), log=0)
    files["AUTO00.DAT"] = patched(files["AUTO00.DAT"], end_of("AUTO") + 4, b"\x01\x02\x03\x04")
    files["SYSTEM.DAT"] = patched(files["SYSTEM.DAT"], end_of("SYSTEM"), b"\x09\0\0\0")      # padding that is not zero
    src = write_set(tmp_path / "in", files)
    code, out, _ = run(capsys, "switch2android", src, tmp_path / "out")
    assert code == 0 and "change: AUTO00.DAT: checksums recalculated" in out
    result = read_set(tmp_path / "out")
    assert S.check_dat("AUTO", result["AUTO00.DAT"]) == [] and S.check_dat("SYSTEM", result["SYSTEM.DAT"]) == []
    assert result["AUTO00.DAT"][end_of("AUTO") + 4:] == result["AUTO00.DAT"][:4]


# ------------------------------------------------------------------------------- R-13: verified before it is written --

def test_nothing_is_written_when_the_output_does_not_validate(switch_dir, tmp_path, capsys, monkeypatch):
    """SPEC-011/R-13"""
    monkeypatch.setattr(S, "verify_files", lambda files, target=None: [("E", "AUTO00.DAT", "boom")])
    code, out, err = run(capsys, "switch2android", switch_dir, tmp_path / "out")
    assert code == 1 and "internal error  AUTO00.DAT: boom" in out
    assert "the output does not validate (nothing is written)" in err and not (tmp_path / "out").exists()


def test_what_is_written_passes_verify_for_its_platform(switch_dir, android_dir, tmp_path, capsys):
    """SPEC-011/R-13"""
    for command, src, target in (("switch2android", switch_dir, "android"), ("android2switch", android_dir, "switch")):
        out_dir = tmp_path / command
        assert run(capsys, command, src, out_dir)[0] == 0
        code, out, _ = run(capsys, "verify", out_dir, "--target", target, "--strict")
        assert code == 0 and "0 errors, 0 warnings" in out


# --------------------------------------------------------------------------------------------- R-14: exit codes ----

def test_verify_exits_1_on_errors_and_0_otherwise(tmp_path, capsys):
    """SPEC-011/R-14"""
    good = write_set(tmp_path / "good", save_set())
    assert run(capsys, "verify", good)[0] == 0
    files = save_set()
    files["AUTO00.DAT"] = patched(files["AUTO00.DAT"], 0x200, b"\x01\x02\x03")
    bad = write_set(tmp_path / "bad", files)
    code, out, _ = run(capsys, "verify", bad)
    assert code == 1 and "E  AUTO00.DAT" in out and "1 errors, 0 warnings" in out


def test_strict_makes_warnings_fail(tmp_path, capsys):
    """SPEC-011/R-14"""
    files = save_set()
    files["AUTO00.DAT"] = patched(files["AUTO00.DAT"], 0x34, struct.pack("<I", 9))          # a wrong type: a warning
    folder = write_set(tmp_path / "w", files)
    code, out, _ = run(capsys, "verify", folder)
    assert code == 0 and "0 errors, 1 warnings" in out
    assert run(capsys, "verify", folder, "--strict")[0] == 1


def test_failures_are_reported_on_stderr_without_a_traceback(switch_dir, tmp_path, capsys):
    """SPEC-011/R-14"""
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "AUTO01.DAT").write_bytes(b"x")
    code, out, err = run(capsys, "switch2android", switch_dir, tmp_path / "out")
    assert code == 1 and out == "" and err.startswith("error: ") and err.count("\n") == 1 and "Traceback" not in err
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    code, out, err = run(capsys, "switch2android", switch_dir, blocker)
    assert code == 1 and err.startswith("error: ")


def test_usage_errors_exit_2_and_help_exits_0(capsys):
    """SPEC-011/R-14: ``main`` always returns an int, argparse's own exits included."""
    assert S.main([]) == 2 and "required" in capsys.readouterr().err
    assert S.main(["bogus"]) == 2
    capsys.readouterr()
    assert S.main(["verify"]) == 2
    assert S.main(["verify", ".", "--target", "ps5"]) == 2
    assert S.main(["switch2android", "only-one-argument"]) == 2
    capsys.readouterr()
    assert S.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "rpl saves" in out and all(c in out for c in ("dump", "verify", "switch2android", "android2switch", "switch2switch"))
    assert S.main(["switch2android", "--help"]) == 0
    out = capsys.readouterr().out
    for option in ("--force", "--dest-system", "--keep-dest-config", "--only-newest-auto", "--no-story", "--skip-invalid",
                   "--keep-log"):
        assert option in out


def test_main_defaults_to_the_command_line_arguments(monkeypatch, capsys):
    """SPEC-011/R-14"""
    monkeypatch.setattr(sys, "argv", ["rpl saves", "--help"])
    assert S.main() == 0
    assert "usage: rpl saves" in capsys.readouterr().out


def test_the_module_runs_with_dash_m():
    """SPEC-011/R-14"""
    done = subprocess.run([sys.executable, "-m", "riviera.saves", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0 and "usage: rpl saves" in done.stdout
    done = subprocess.run([sys.executable, "-m", "riviera.saves", "verify", str(ROOT / "no-such-folder")], cwd=ROOT,
                          capture_output=True, text=True)
    assert done.returncode == 1 and "error: no such folder" in done.stderr


def test_the_module_needs_nothing_but_the_standard_library():
    """SPEC-011/R-15: the converter is stdlib only, so it also runs where Pillow is not installed."""
    import ast
    tree = ast.parse(Path(S.__file__).read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.level == 0}
    assert imported <= set(sys.stdlib_module_names)
