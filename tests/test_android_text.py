"""Tests of riviera.android.text: composition of Android-only text, the dialogue and interface rewraps, references to the official
script, the label fixes and the writing of the appended segment (SPEC-014)."""

import hashlib
import json
import struct

import pytest

import synth
from riviera import nso as nsomod
from riviera.android import text
from riviera.android.elf import PF_R, PF_X, Elf
from riviera.android.hooks import RESERVE
from riviera.packs import fingerprint
from test_android_elf import make_library


class FakeMetrics:
    """Every character is 100 units wide and a space 32: lines are easy to count."""

    def glyph(self, ch):
        return 32 if ch in " 　" else 100

    def line(self, s):
        return sum(self.glyph(c) for c in s)


M = FakeMetrics()
JA = "テスト"
JB = "メニュー"


def test_android_only_text_fits_one_line_when_it_can():
    """SPEC-014/R-6: a text that fits stays on one line."""
    out, warns = text.compose_android(JA + JB, ["hi"], M, dialog_cap=2000, soft=1.12)      # 7 kana = 462 units of width; "hi" is 200
    assert out == "hi" and warns == []


def test_android_only_text_wraps_at_the_width_of_the_japanese():
    """SPEC-014/R-6: without a cap the box is as wide as the longest Japanese line times 66."""
    # 2 Japanese characters x JP_CELL = 132 units of width: every word of 5 characters (500) is too wide, so one word per line;
    # the original has one line, so the warning says it needed more
    out, warns = text.compose_android(JA[:2], ["aaaaa bbbbb"], M, dialog_cap=2000, soft=1.12)
    assert out == "aaaaa;bbbbb"
    assert warns and "2 lines (max 1)" in warns[0]


def test_android_only_text_keeps_tags_and_uses_the_dialogue_band_for_voices():
    """SPEC-014/R-6: the tags and separators of the Japanese are kept; voiced and tagged segments use the dialogue band."""
    raw = "V(114b_0069)" + JA + ",c1" + JB
    out, warns = text.compose_android(raw, ["one two three four five", "x"], M, dialog_cap=1300, soft=1.0)
    first, second = out.split(",", 1)
    assert first.startswith("V(114b_0069)") and second == "c1x"
    assert first.count(";") == 1 and not warns                       # 23 characters do not fit 1300 units: two lines are allowed for a voice


def test_android_only_text_measures_numbers_as_three_digits_and_keeps_the_format():
    """SPEC-014/R-6: a %s is measured as a three-digit number and stays a %s in the final text."""
    out, _ = text.compose_android(JA * 12, ["Raises STR by %s for %s counts"], M, dialog_cap=2000, soft=1.12, cap=1700)
    assert out.count("%s") == 2


def test_the_segments_of_the_text_must_be_as_many_as_the_japanese_has():
    """SPEC-014/R-6: a text with another number of segments than the original is an error, not a silent truncation."""
    raw = "c1" + JA + ",c1" + JB
    entries = {fingerprint(raw): {"t": ["only one"]}}
    with pytest.raises(text.TextError, match="2"):
        text.android_only_texts([(0x10, raw)], set(), entries, M, {(12, ""): (2, 1300)}, 1.12, say=lambda *_: None)


def test_rewrap_dialog_never_leaves_three_lines():
    """SPEC-014/R-4: no dialogue page keeps more than two lines."""
    rows = [{"block": 12, "en": "a,b"}, {"block": 12, "en": "a"}]
    texts = {0: "aaaa bbbb;cccc dddd;eeee ffff", 1: "short;text"}
    n = text.rewrap_dialog(rows, texts, M)
    assert n == 1
    assert texts[0].count(";") == 1                                  # two lines now
    assert texts[1] == "short;text"                                  # already fine: untouched
    assert sorted(texts[0].replace(";", " ").split()) == ["aaaa", "bbbb", "cccc", "dddd", "eeee", "ffff"]


def test_rewrap_dialog_ignores_other_blocks():
    """SPEC-014/R-4: only the dialogue blocks are limited to two lines."""
    rows = [{"block": 37, "en": "x"}]
    texts = {0: "a;b;c"}
    assert text.rewrap_dialog(rows, texts, M) == 0 and texts[0] == "a;b;c"


def test_rewrap_ui_returns_long_lines_to_the_english_lines():
    """SPEC-014/R-5: an interface text whose English has two lines goes back to two lines."""
    rows = [{"block": 37, "en": "Do you want to overwrite;this save data?"}]
    texts = {0: "aaaaaaaaaa bbbbbbbbbb cccccccccc dddddddddd"}      # one line of 4 words: much wider than the English lines
    assert text.rewrap_ui(rows, texts, M) == 1
    assert texts[0].count(";") == 1


def test_rewrap_ui_leaves_bullet_lists_alone():
    """SPEC-014/R-5: lists of bullets are left as they are."""
    rows = [{"block": 37, "en": "・a;・b"}]
    texts = {0: "・one two three four five six seven;・x"}
    assert text.rewrap_ui(rows, texts, M) == 0


# ------------------------------------------------- references to the donor --

UNITS = {"1111111111111111": ["Inflicts ZZ status"], "2222222222222222": ["Right, off we go!", "Touch the screen."]}


def test_a_reference_is_resolved_from_the_donor_script():
    """SPEC-014/R-9: an entry that is the official English holds a reference, resolved with the strings of the user's Switch dump."""
    entries = {"a": {"k": "a", "ref": "1111111111111111", "cap": 1700},
               "b": {"k": "b", "t": [{"ref": "2222222222222222", "seg": 0}, "my own text"], "force": True},
               "c": {"k": "c", "t": ["plain"]}}
    out = text.resolve_entries(entries, UNITS)
    assert out["a"] == {"k": "a", "t": ["Inflicts ZZ status"], "cap": 1700}
    assert out["b"]["t"] == ["Right, off we go!", "my own text"] and out["b"]["force"] is True
    assert out["c"]["t"] == ["plain"]


def test_a_reference_without_a_dump_fails_clearly():
    """SPEC-014/R-9: with no Switch dump a reference cannot be resolved, and the message names the entry."""
    with pytest.raises(text.TextError, match="no Switch dump"):
        text.resolve_entries({"a": {"k": "a", "ref": "1111111111111111"}}, None)
    text.resolve_entries({"a": {"k": "a", "t": ["no reference, no donor needed"]}}, None)


def test_a_reference_the_dump_does_not_have_fails_clearly():
    """SPEC-014/R-9: a reference the dump has no string for is an error that names it (another version of the game)."""
    with pytest.raises(text.TextError, match="9999999999999999"):
        text.resolve_entries({"a": {"k": "a", "ref": "9999999999999999"}}, UNITS)
    with pytest.raises(text.TextError, match="segment 5"):
        text.resolve_entries({"a": {"k": "a", "t": [{"ref": "1111111111111111", "seg": 5}]}}, UNITS)


def test_an_entry_needs_a_text_or_a_reference(tmp_path):
    """SPEC-014/R-9: the file format: every entry has ``t`` or ``ref``."""
    f = tmp_path / "text.jsonl"
    f.write_text(json.dumps({"k": "a"}) + "\n", encoding="utf-8")
    with pytest.raises(text.TextError, match="neither"):
        text.read_android_text(f)


def test_donor_units_are_the_readable_segments_of_each_switch_string():
    """SPEC-014/R-9: the references are fingerprints of the raw Switch strings, which give their readable segments."""
    rows = [{"block": 0, "row": 0, "en": "Yes"}, {"block": 0, "row": 1, "en": "V(112b_0000)How are you,V(112b_0001)friend?"}]
    units = text.donor_units(rows)
    assert units[fingerprint("Yes")] == ["Yes"]
    assert units[fingerprint(rows[1]["en"])] == ["How are you", "friend?"]


# ------------------------------------------------------------ label fixes --

class FakeNso:
    def __init__(self, mem):
        self.mem = mem


def sha(s):
    return hashlib.sha1(s.encode()).hexdigest()


def test_label_fixes_find_both_sides_by_hash(monkeypatch):
    """SPEC-014/R-10: the labels are found by the SHA-1 of their text in the library and in the Switch executable."""
    monkeypatch.setattr(text, "ENGLISH_FIXES", {sha("ZZ old label"): sha("ZZ new label")})
    lib, info = make_library(strings=[b"first", b"ZZ old label", b"last one"], relocs=[(0, 0), (1, 1), (2, 1)])
    nso = FakeNso(b"\0\0padding\0ZZ new label\0more\0")
    e = Elf(lib)
    got = text.english_fixes(e, nso, e.relative_relocs())
    assert got == [(info["slots"][1], "ZZ new label"), (info["slots"][2], "ZZ new label")]


def test_label_fixes_refuse_a_library_without_the_label(monkeypatch):
    """SPEC-014/R-10: a library without the label is refused."""
    monkeypatch.setattr(text, "ENGLISH_FIXES", {sha("ZZ old label"): sha("ZZ new label")})
    lib, _ = make_library(strings=[b"something else"], relocs=[(0, 0)])
    e = Elf(lib)
    with pytest.raises(text.TextError):
        text.english_fixes(e, FakeNso(b"\0ZZ new label\0"), e.relative_relocs())


def test_label_fixes_refuse_an_ambiguous_label(monkeypatch):
    """SPEC-014/R-10: a label that appears twice is refused."""
    monkeypatch.setattr(text, "ENGLISH_FIXES", {sha("ZZ old label"): sha("ZZ new label")})
    lib, _ = make_library(strings=[b"ZZ old label", b"ZZ old label"], relocs=[(0, 0), (1, 1)])
    e = Elf(lib)
    with pytest.raises(text.TextError):
        text.english_fixes(e, FakeNso(b"\0ZZ new label\0"), e.relative_relocs())


def test_shipped_label_fixes_store_no_text():
    """SPEC-014/R-10: the shipped table holds SHA-1 digests only."""
    for old, new in text.ENGLISH_FIXES.items():
        assert len(old) == len(new) == 40 and int(old, 16) >= 0 and int(new, 16) >= 0


# -------------------------------------------------------------- literals --

def test_literals_are_zero_padded_and_cannot_grow():
    """SPEC-014/R-8: a literal is written over the original, zero padded; one that needs more bytes is an error."""
    raw = JA + JB                                                    # 21 bytes of UTF-8
    entries = {fingerprint(raw): {"k": fingerprint(raw), "t": ["Hello"], "lit": True}}
    out = text.android_literals([(0x1000, raw)], entries)
    assert out[0x1000] == b"Hello" + b"\0" * (len(raw.encode()) - 5)
    entries[fingerprint(raw)]["t"] = ["x" * 40]
    with pytest.raises(text.TextError):
        text.android_literals([(0x1000, raw)], entries)


def test_android_only_texts_skip_aligned_slots_unless_forced():
    """SPEC-014/R-7: an Android-only entry replaces slots with no Switch counterpart, and aligned ones only if it carries force."""
    a, b, c = f"c1{JA}", f"c1{JB}", "c1" + JA + JB
    entries = {fingerprint(a): {"t": ["one"]}, fingerprint(b): {"t": ["two"], "force": True}}
    caps = {(12, ""): (2, 1300)}
    slots = [(0x10, a), (0x18, b), (0x20, c)]
    got = text.android_only_texts(slots, {0x10, 0x18}, entries, M, caps, 1.12, say=lambda *_: None)
    assert got == [(0x18, "c1two")]                                  # 0x10 aligned (kept), 0x18 aligned but forced, 0x20 untranslated


# ----------------------------------------------------------------- apply --

def test_apply_appends_the_segment_and_redirects_the_pointers():
    """SPEC-014/R-2: strings go into the appended segment after the room for the hooks; equal texts share a copy; both the relocation and the stored value change."""
    lib, info = make_library(strings=[b"one", b"two", b"lit"], relocs=[(0, 0), (1, 1)], tail=0x333)
    e = Elf(lib)
    plan = text.TextPlan(strings=[(info["slots"][0], "NEW1"), (info["slots"][1], "NEW1"), (0xdead0, "nowhere")],
                         literals={info["strings"][2]: b"LIT"})
    off, va = text.apply(e, plan, say=lambda *_: None)
    again = Elf(bytes(e.data))
    seg = next(p for p in again.loads if p.vaddr == va)
    assert seg.offset == off and seg.flags == PF_R | PF_X and seg.filesz == RESERVE + len(b"NEW1\0")
    assert not any(e.data[off:off + RESERVE])                        # the first RESERVE bytes are left for the hooks
    relocs = again.relative_relocs()
    new = va + RESERVE
    assert [relocs[s][1] for s in info["slots"]] == [new, new]       # both slots share the single copy of the text
    assert again.read(new, 5) == b"NEW1\0"
    assert struct.unpack("<Q", again.read(info["slots"][0], 8))[0] == new
    assert again.read(info["strings"][2], 3) == b"LIT"               # the literal was rewritten in place
    assert again.read(info["strings"][0], 3) == b"one"               # the original strings stay where they were


def test_apply_checks_the_skill_order_flags(monkeypatch):
    """SPEC-014/R-11: the order flags are only cleared if they hold the value this version of the app has."""
    lib, _ = make_library(tail=0x10)
    e = Elf(lib)
    monkeypatch.setattr(text, "SKILL_FLAGS", 0x1000)                 # a place where the flags are not what the version expects
    with pytest.raises(text.TextError):
        text.apply(e, text.TextPlan(swap_skill_order=True), say=lambda *_: None)


def test_apply_clears_the_skill_order_flags_only_when_asked(monkeypatch):
    """SPEC-014/R-11: with Android-only text the flags of the skill descriptions that said "turns first" are cleared; otherwise left alone."""
    words = {0x1100 + 16 * i: struct.pack("<I", 1) for i in range(3)}
    monkeypatch.setattr(text, "SKILL_FLAGS", 0x1100)
    monkeypatch.setattr(text, "SKILL_SWAP", range(0, 3))
    lib, _ = make_library(words=words, tail=0x10)
    e = Elf(lib)
    text.apply(e, text.TextPlan(), say=lambda *_: None)
    assert [e.u32(0x1100 + 16 * i) for i in range(3)] == [1, 1, 1]
    text.apply(Elf(lib), text.TextPlan(), say=lambda *_: None)
    e2 = Elf(lib)
    text.apply(e2, text.TextPlan(swap_skill_order=True), say=lambda *_: None)
    assert [e2.u32(0x1100 + 16 * i) for i in range(3)] == [0, 0, 0]


# ------------------------------------------------------------------- plan --

def test_plan_keeps_the_donor_english_where_the_pack_has_no_translation(tmp_path, dump, monkeypatch):
    """SPEC-014/R-3: a row the pack does not translate keeps the English of the donor; the ones it translates get the translation."""
    monkeypatch.setattr(text, "ENGLISH_FIXES", {})
    lang = synth.make_lang(tmp_path / "langs", "yy", {"Yes": ["Sí"]})
    lib, info = make_library(strings=["はい".encode(), "いいえ".encode()], relocs=[(0, 0), (1, 1)])
    elf = Elf(lib)
    plan = text.plan(elf, nsomod.Nso(dump.exefs / "main"), lang, say=lambda *_: None)
    got = dict(plan.strings)
    assert got[info["slots"][0]] == "Sí" and got[info["slots"][1]] == "No"
