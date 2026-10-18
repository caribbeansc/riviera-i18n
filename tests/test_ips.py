"""SPEC-002: writing strings into the executable and the IPS patch."""

import pytest

import synth
from riviera import ips
from riviera import nso as N


def test_encode_follows_the_engine_conventions():
    """SPEC-002/R-9: the ASCII comma separates segments, so the one in the text goes full-width."""
    assert ips.encode("Hola, mundo") == "Hola， mundo"
    assert ips.encode("Bien...") == "Bien..."
    assert ips.encode("Bien…") == "Bien＿"
    assert ips.encode("It's \"ok\"") == "It’s ”ok”"


def test_encode_protects_the_engine_from_printf():
    """SPEC-002/R-9: the engine runs printf on a string; a bare % followed by a letter would print a number."""
    assert ips.encode("75% del MAX") == "75％ del MAX"
    assert ips.encode("%d turnos") == "%d turnos"
    assert ips.encode("%s de %3d") == "%s de %3d"


def test_encode_wide_and_strip_accents():
    """SPEC-002/R-9"""
    assert ips.encode("Hi 1", "wide") == "Ｈｉ　１"
    assert ips.encode("¿Qué?", strip_accents=True) == "?Que?"


def test_writes_refuse_to_overlap():
    """SPEC-002/R-10"""
    w = ips.Writes()
    w.put(10, b"abcd")
    w.put(14, b"ef")
    with pytest.raises(ValueError):
        w.put(12, b"xx")


def test_ips_roundtrip_and_merging():
    """SPEC-002/R-10: nearby writes merge into one record; applying the patch gives the same image."""
    orig = bytes(range(256)) * 4
    w = {5: b"AB", 7: b"CD", 100: b"Z", 600: b"hello"}
    patch = ips.to_ips(w, orig)
    assert patch.startswith(b"PATCH") and patch.endswith(b"EOF")
    expected = bytearray(orig)
    for off, data in w.items():
        expected[off:off + len(data)] = data
    assert ips.apply_ips(patch, orig) == bytes(expected)
    assert patch.count(b"\x00\x05\x00\x07") == 0                         # 5 and 7 merged into a single record


def test_ips_never_writes_the_eof_marker_as_an_offset():
    """SPEC-002/R-10: offset 0x454F46 spells EOF and would end the patch early."""
    orig = bytes(0x455000)
    patch = ips.to_ips({0x454F46: b"data"}, orig)
    assert ips.apply_ips(patch, orig)[0x454F46:0x454F4A] == b"data"
    assert patch.count(b"EOF") == 1


def test_apply_rejects_something_that_is_not_ips():
    """SPEC-002/R-10"""
    with pytest.raises(ValueError):
        ips.apply_ips(b"NOPE", b"")


def _nso(blocks=None):
    s = synth.make_nso(blocks or synth.sample_blocks())
    return s, N.Nso.from_image(s.image, s.build.build_id)


def test_place_shrinks_in_place_and_keeps_the_rest():
    """SPEC-002/R-11"""
    s, n = _nso()
    rows = N.read_rows(n)
    slot = rows[0]["slots"][0]                                         # "Hello"
    want = {slot: (n.relocs[slot], b"Hi")}
    writes, placed, relocate, unplaced, pool = ips.place(n, want)
    assert placed[slot] == n.relocs[slot] and not relocate and not unplaced
    assert writes[N.HEADER + n.relocs[slot]] == b"Hi\0"
    assert any(start == n.relocs[slot] + 3 for start, _ in pool)       # the freed tail becomes free space


def test_place_moves_a_longer_string_into_free_space():
    """SPEC-002/R-11"""
    s, n = _nso()
    rows = N.read_rows(n)
    slot = rows[0]["slots"][0]
    new = b"A much longer translation than the English"
    writes, placed, relocate, unplaced, pool = ips.place(n, {slot: (n.relocs[slot], new)}, extra_pool=[(0x5800, 0x5900)])
    assert placed[slot] == 0x5800 and relocate == [slot] and not unplaced
    assert writes[N.HEADER + 0x5800] == new + b"\0"
    import struct
    assert struct.unpack("<q", writes[N.HEADER + n.rela_entry[slot] + 16])[0] == 0x5800     # the relocation now points there


def test_place_reports_what_has_no_room():
    """SPEC-002/R-11"""
    s, n = _nso()
    slot = N.read_rows(n)[0]["slots"][0]
    _, _, _, unplaced, _ = ips.place(n, {slot: (n.relocs[slot], b"x" * 500)})
    assert unplaced == [slot]


def test_a_string_the_code_uses_is_never_overwritten():
    """SPEC-002/R-12: the "/" the code builds paths with was once overwritten and the game died three seconds after booting."""
    blocks = [{"header": False, "en": ["/", "Other"], "jp": ["あ", "い"], "kr": ["가", "나"], "tc": ["甲", "乙"]}]
    s, n = _nso(blocks)
    slot = N.read_rows(n)[0]["slots"][0]
    assert n.text(n.relocs[slot]) == "/" and n.relocs[slot] == s.protected_addr
    assert ips.code_uses(n, s.protected_addr, 1)
    writes, placed, relocate, unplaced, _ = ips.place(n, {slot: (n.relocs[slot], b"X")}, extra_pool=[(0x5800, 0x5900)])
    assert placed[slot] == 0x5800 and relocate == [slot]
    assert N.HEADER + s.protected_addr not in writes


def test_strings_the_code_does_not_use_are_not_flagged():
    """SPEC-002/R-12"""
    s, n = _nso()
    slot = N.read_rows(n)[0]["slots"][0]
    assert not ips.code_uses(n, n.relocs[slot], len("Hello"))
