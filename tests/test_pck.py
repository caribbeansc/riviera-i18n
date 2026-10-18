"""SPEC-001: the .pck packages."""

import pytest

import synth
from riviera import pck


def test_roundtrip():
    """SPEC-001/R-7"""
    blob = synth.make_pck({"a.webp": b"AAA", "b.webp": b"B" * 10})
    data0, ents = pck.read_pck(blob)
    assert pck.names(ents) == ["a.webp", "b.webp"]
    assert [e[1] for e in ents] == [b"AAA", b"B" * 10]
    assert pck.write_pck(data0, ents) == blob


def test_entry_can_change_size():
    """SPEC-001/R-7: the engine draws every picture at its own size, so an entry may grow."""
    blob = synth.make_pck({"a.webp": b"AAA", "b.webp": b"BB"})
    data0, ents = pck.read_pck(blob)
    ents[0][1] = b"A" * 100
    again = pck.read_pck(pck.write_pck(data0, ents))[1]
    assert [e[1] for e in again] == [b"A" * 100, b"BB"]


def test_alignment_pads_each_entry():
    """SPEC-001/R-8"""
    blob = synth.make_pck({"a.webp": b"AAA", "b.webp": b"BB"})
    data0, ents = pck.read_pck(blob)
    aligned = pck.write_pck(data0, ents, align=4)
    import struct
    offsets = [struct.unpack_from("<II", aligned, 8 + i * pck.ENTRY + 64)[1] for i in range(2)]
    assert all(o % 4 == 0 for o in offsets)
    assert [e[1] for e in pck.read_pck(aligned)[1]] == [b"AAA", b"BB"]


def test_bad_header_is_refused():
    """SPEC-001/R-7"""
    with pytest.raises(ValueError):
        pck.write_pck(8, [[b"x".ljust(64, b"\0"), b"data"]])             # data0 does not fit the entry table
