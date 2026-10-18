"""SPEC-002: reading the script out of the executable."""

import struct

import pytest

import synth
from riviera import nso as N


def test_lz4_literals():
    """SPEC-002/R-1"""
    assert N.lz4_block(bytes([0x50]) + b"hello", 5) == b"hello"


def test_lz4_match_and_overlap():
    """SPEC-002/R-1: a match may overlap what it is copying (offset smaller than length)."""
    block = bytes([0x32]) + b"abc" + bytes([3, 0]) + bytes([0x10]) + b"x"
    assert N.lz4_block(block, 10) == b"abcabcabcx"
    # offset 1, length 9 after one literal: "a" repeated
    block = bytes([0x15]) + b"a" + bytes([1, 0]) + bytes([0x10]) + b"z"
    assert N.lz4_block(block, 1 + 9 + 1) == b"a" * 10 + b"z"


def test_lz4_size_is_checked():
    """SPEC-002/R-1"""
    with pytest.raises(ValueError):
        N.lz4_block(bytes([0x50]) + b"hello", 6)


def test_load_nso_and_build_id(tmp_path):
    """SPEC-002/R-2"""
    s = synth.make_nso(synth.sample_blocks())
    path = synth.write_nso(tmp_path / "main", s)
    image, build_id = N.load_nso(path)
    assert build_id.startswith("AB" * 20)
    assert image[N.HEADER:] == s.image[N.HEADER:]
    assert N.Nso(path).relocs                                            # MOD0 / RELA were found


def test_not_an_nso(tmp_path):
    """SPEC-002/R-2"""
    (tmp_path / "main").write_bytes(b"ELF!" + bytes(100))
    with pytest.raises(ValueError):
        N.load_nso(tmp_path / "main")


def test_table_and_blocks_are_found_by_content():
    """SPEC-002/R-3: no fixed addresses; blocks with and without a header."""
    s = synth.make_nso(synth.sample_blocks())
    n = N.Nso.from_image(s.image, s.build.build_id)
    t0, count = N.find_table(n)
    assert (t0, count) == (synth.SLOTS_AT, 24)
    blocks = N.find_blocks(n, t0, count)
    assert [(m, hdr) for _, m, hdr in blocks] == [(3, True), (2, False)]


def test_rows_line_up_across_languages():
    """SPEC-002/R-4"""
    s = synth.make_nso(synth.sample_blocks())
    n = N.Nso.from_image(s.image, s.build.build_id)
    rows = N.read_rows(n)
    assert [(r["block"], r["row"], r["en"], r["jp"]) for r in rows] == [(r["block"], r["row"], r["en"], r["jp"]) for r in s.rows]
    assert all(len(r["slots"]) == 4 for r in rows)
    assert rows[1]["slots"][1] - rows[1]["slots"][0] == 3 * 8             # the Japanese row k is `n` slots after the English one


def test_slots_are_relocated_pointers():
    """SPEC-002/R-5"""
    s = synth.make_nso(synth.sample_blocks())
    n = N.Nso.from_image(s.image, s.build.build_id)
    row = N.read_rows(n)[0]
    slot = row["slots"][0]
    assert slot in n.rela_entry
    off, info, addend = struct.unpack_from("<QQq", n.mem, n.rela_entry[slot])
    assert (off, info, addend) == (slot, N.R_AARCH64_RELATIVE, n.relocs[slot])
    assert n.text(n.relocs[slot]) == "Hello"
