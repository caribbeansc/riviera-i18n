"""Tests of riviera.android.hooks: the installer on a synthetic library, and the sanity of the shipped blob."""

import json
import struct

import pytest

from riviera.android import hooks as hk
from riviera.android.elf import Elf
from test_android_elf import make_library

BASE = 0x40000                                      # where the synthetic blob is "linked"


def fake_hooks(slot_word=b"\x1f\x20\x03\xd5"):
    """A tiny blob and description with one post hook, one skip hook, one replaced function, one patch and the tables."""
    blob = bytearray(0x200)
    blob[0x10:0x14] = b"cave"                        # marker: the code of the cave of hook "a" starts here
    blob[0x24:0x28] = slot_word                      # the nop slot of hook "a"
    meta = {
        "version": 1, "library_sha256": "0" * 64, "base": BASE, "size": len(blob),
        "hooks": [
            {"name": "a", "addr": 0x1100, "kind": "post", "cave": 0x10, "slot": 0x24, "orig": None, "resume": None, "resume_orig": None},
            {"name": "b", "addr": 0x1200, "kind": "skip", "cave": 0x40, "slot": None, "orig": None, "resume": 0x1210, "resume_orig": None},
        ],
        "replace": [{"addr": 0x1300, "to": 0x80, "orig": None, "what": "hk_fn"}],
        "patches": [{"addr": 0x1400, "orig": None, "new": "01020304", "what": "one word"}],
        "tables": {"M1": {"off": 0x100, "first": 251, "count": 2, "size": 12}, "M2": {"off": 0x110, "first": 2204, "count": 1, "size": 6},
                   "M3": {"off": 0x118, "first": 2378, "count": 1, "size": 6}, "charset": {"off": 0x120, "size": 16}},
        "init_charset": {"addr": 0x1500, "reg": 1, "orig": None},
    }
    return blob, meta


WORDS = {0x1100: b"\x11\x11\x11\x11", 0x1200: b"\x22\x22\x22\x22", 0x1210: b"\x33\x33\x33\x33", 0x1300: b"\x44\x44\x44\x44",
         0x1400: b"\x55\x55\x55\x55", 0x1500: b"\x66\x66\x66\x66\x77\x77\x77\x77"}


def with_fingerprints(meta, words=WORDS):
    for h in meta["hooks"]:
        h["orig"] = hk.site_fingerprint(h["addr"], words[h["addr"]])
        if h["resume"]:
            h["resume_orig"] = hk.site_fingerprint(h["resume"], words[h["resume"]])
    for r in meta["replace"]:
        r["orig"] = hk.site_fingerprint(r["addr"], words[r["addr"]])
    for p in meta["patches"]:
        p["orig"] = hk.site_fingerprint(p["addr"], words[p["addr"]])
    meta["init_charset"]["orig"] = hk.site_fingerprint(0x1500, words[0x1500])
    return meta


def library():
    lib, _ = make_library(words=WORDS, tail=0x4000)
    e = Elf(lib)
    off, va = e.next_segment_address()
    e.data.extend(b"\0" * (off - len(e.data) + 0x1000))
    return e, off, va


def tables():
    return {"M1": bytes(range(12)), "M2": bytes(range(20, 26)), "M3": bytes(range(30, 36))}


def test_branch_and_adrp_encoding():
    assert hk.b_insn(0x1000, 0x1000 + 8) == struct.pack("<I", 0x14000002)
    assert hk.b_insn(0x1008, 0x1000) == struct.pack("<I", 0x14000000 | (-2 & 0x3FFFFFF))
    with pytest.raises(hk.HooksError):
        hk.b_insn(0x1000, 0x1000 + (1 << 28))
    with pytest.raises(hk.HooksError):
        hk.b_insn(0x1000, 0x1002)
    adrp, add = struct.unpack("<II", hk.adrp_add(0x1000, 0x5123, 3, 4))
    assert adrp & 0x9F000000 == 0x90000000 and adrp & 31 == 3 and (adrp >> 5) & 0x7FFFF == 1       # 4 pages ahead: immlo=0, immhi=1
    assert (add >> 10) & 0xFFF == 0x123 and (add >> 5) & 31 == 4 and add & 31 == 3


def test_fingerprint_depends_on_address_and_word():
    assert hk.site_fingerprint(0x1000, b"\0\0\0\0") != hk.site_fingerprint(0x1004, b"\0\0\0\0")
    assert hk.site_fingerprint(0x1000, b"\0\0\0\0") != hk.site_fingerprint(0x1000, b"\0\0\0\1")
    assert len(hk.site_fingerprint(0x1000, b"abcd")) == 12


def test_install_hooks_the_game_and_fills_the_holes():
    """SPEC-015/R-2, SPEC-015/R-5: the tables and the character string are copied into the holes, the game branches to the caves and each cave gets the instruction it displaced."""
    e, off, va = library()
    blob, meta = fake_hooks()
    meta = with_fingerprints(meta)
    meta["base"] = va
    summary = hk.install(e, off, va, tables=tables(), charset=b"charset!", hooks=hk.Hooks(bytes(blob), meta))
    assert summary == {"hooks": 2, "replaced": 1, "patches": 1, "charset": True}
    assert e.read(0x1100, 4) == hk.b_insn(0x1100, va + 0x10)             # the game branches to the cave
    assert e.read(0x1200, 4) == hk.b_insn(0x1200, va + 0x40)
    assert e.read(0x1300, 4) == hk.b_insn(0x1300, va + 0x80)             # a replaced function jumps to its hook
    assert e.read(0x1400, 4) == bytes.fromhex("01020304")                # a one-word patch
    placed = bytes(e.data[off:off + len(blob)])
    assert placed[0x10:0x14] == b"cave"                                  # the blob is where the appended segment starts
    assert placed[0x24:0x28] == WORDS[0x1100]                            # the displaced instruction comes from the user's own library
    assert placed[0x100:0x10c] == tables()["M1"] and placed[0x110:0x116] == tables()["M2"] and placed[0x118:0x11e] == tables()["M3"]
    assert placed[0x120:0x128] == b"charset!" and placed[0x128] == 0
    adrp, add = struct.unpack("<II", e.read(0x1500, 8))                  # FNT_init now loads the extended string
    assert (add >> 10) & 0xFFF == (va + 0x120) & 0xFFF


def test_install_without_charset_leaves_fnt_init_alone():
    """SPEC-015/R-6: without an extended character string FNT_init is not touched and its area stays empty."""
    e, off, va = library()
    blob, meta = fake_hooks()
    meta = with_fingerprints(meta)
    meta["base"] = va
    summary = hk.install(e, off, va, tables=tables(), hooks=hk.Hooks(bytes(blob), meta))
    assert summary["charset"] is False
    assert e.read(0x1500, 8) == WORDS[0x1500]
    assert not any(e.data[off + 0x120:off + 0x130])


def test_install_refuses_another_version_and_writes_nothing():
    """SPEC-015/R-3: a site that does not hold the expected instruction stops the install before anything is written."""
    e, off, va = library()
    blob, meta = fake_hooks()
    meta = with_fingerprints(meta, {**WORDS, 0x1200: b"\x99\x99\x99\x99"})     # the hook "b" expects another word than the library has
    meta["base"] = va
    before = bytes(e.data)
    with pytest.raises(hk.HooksError, match="0x1200"):
        hk.install(e, off, va, tables=tables(), hooks=hk.Hooks(bytes(blob), meta))
    assert bytes(e.data) == before


def test_install_checks_the_segment_address_and_the_table_sizes():
    """SPEC-015/R-4, SPEC-015/R-2: the blob is linked for one address, and every table must have the size it was made for."""
    e, off, va = library()
    blob, meta = fake_hooks()
    meta = with_fingerprints(meta)
    with pytest.raises(hk.HooksError, match="linked for"):
        hk.install(e, off, va, tables=tables(), hooks=hk.Hooks(bytes(blob), {**meta, "base": va + 0x4000}))
    meta["base"] = va
    bad = {**tables(), "M1": b"short"}
    with pytest.raises(hk.HooksError, match="M1"):
        hk.install(e, off, va, tables=bad, hooks=hk.Hooks(bytes(blob), meta))
    with pytest.raises(hk.HooksError, match="does not fit"):
        hk.install(e, off, va, tables=tables(), charset=b"x" * 40, hooks=hk.Hooks(bytes(blob), meta))


# ------------------------------------------------------- the shipped blob --

def test_shipped_blob_matches_its_description():
    """SPEC-015/R-4: hooks.bin and hooks.json agree, and the blob fits the space reserved at the start of the segment."""
    h = hk.load()
    m = h.meta
    assert len(h.blob) == m["size"] <= hk.RESERVE
    assert m["base"] % 0x4000 == 0
    assert len(m["library_sha256"]) == 64
    assert {x["name"] for x in m["hooks"]} >= {"code_pos", "code_adv", "sys_pos", "sys_adv", "sys_pitch", "conf_box", "conf_text", "msg_scale"}
    for x in m["hooks"]:
        assert 0 <= x["cave"] < m["size"] and len(x["orig"]) == 12
        assert (x["slot"] is None) == (x["kind"] == "skip")
    for x in m["replace"] + m["patches"]:
        assert len(x["orig"]) == 12


def test_shipped_blob_holds_no_game_data():
    """SPEC-015/R-1: the shipped blob has empty holes and nop slots (everything the game owns is filled from the user's files)."""
    h = hk.load()
    for name, spec in h.meta["tables"].items():
        assert not any(h.blob[spec["off"]:spec["off"] + spec["size"]]), f"table {name} is not empty"
    nop = bytes.fromhex("1f2003d5")
    for x in h.meta["hooks"]:
        if x["slot"] is not None:
            assert h.blob[x["slot"]:x["slot"] + 4] == nop, f"the slot of {x['name']} is not a nop"


def test_shipped_description_has_no_original_words():
    """SPEC-015/R-1: hooks.json keeps fingerprints, not instructions."""
    """Only short fingerprints of the original instructions are kept, never the instructions themselves."""
    text = (hk.DATA_DIR / "hooks.json").read_text(encoding="utf-8")
    meta = json.loads(text)
    for x in meta["hooks"]:
        assert set(x) == {"name", "addr", "kind", "cave", "slot", "orig", "resume", "resume_orig"}


def test_description_matches_the_sources_it_was_made_from():
    """SPEC-015/R-7: the geometry of the tables in hooks.json is the one hooks.c declares (the files are reproducible with build_hooks.py)."""
    import re
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "tools" / "android" / "hooks.c").read_text(encoding="utf-8")
    meta = hk.load().meta

    def define(name):
        return int(re.search(r"^#define\s+%s\s+(\d+)" % name, source, re.M).group(1))

    for n in ("M1", "M2", "M3"):
        spec = meta["tables"][n]
        assert (spec["first"], spec["count"], spec["size"]) == (define(n + "_FIRST"), define(n + "_COUNT"), 6 * define(n + "_COUNT"))
    assert meta["tables"]["charset"]["size"] == define("CHARSET_MAX")
