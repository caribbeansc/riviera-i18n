"""Tests of riviera.android.align on synthetic data: the order-based alignment of Android slots with Switch rows."""

from riviera.android import align
from riviera.android.elf import Elf
from test_android_elf import make_library

JA = "テスト"            # three kana: "test"
JB = "メニュー"
JC = "カード"
JD = "ドア"


def rows(*jp, block=11):
    return [{"jp": j, "en": f"en{i}", "block": block} for i, j in enumerate(jp)]


def test_is_japanese():
    assert align.is_japanese(JA)
    assert align.is_japanese("V(001_0001)hello")        # a voice tag marks script text even without kana
    assert not align.is_japanese("plain ascii")


def test_lis_keeps_the_longest_increasing_run():
    vals = [5, 1, 2, 9, 3, 4, 0, 6]
    chosen = [vals[i] for i in align.lis(vals)]
    assert chosen == sorted(chosen) and len(chosen) == 5          # 1 2 3 4 6
    assert align.lis([]) == []


def test_unique_texts_are_anchors_and_follow_the_order():
    """SPEC-014/R-1: anchors, then the order of the Switch rows."""
    r = rows(JA, JB, JC, JD)
    slots = [(0x100, JA), (0x108, JB), (0x110, JC), (0x118, JD)]
    got = align.align(slots, r)
    assert got == [(0, "exact"), (1, "exact"), (2, "exact"), (3, "exact")]


def test_repeated_text_takes_the_row_after_the_previous_one():
    """SPEC-014/R-1: a repeated text takes the first row after the previous one."""
    r = rows(JA, JB, JA, JC, JA)                                    # JA appears three times
    slots = [(0x100, JA), (0x108, JB), (0x110, JA), (0x118, JC), (0x120, JA)]
    got = align.align(slots, r)
    assert [g for g, _ in got] == [0, 1, 2, 3, 4]
    assert got[1][1] == "exact" and got[0][1] == "order"


def test_text_missing_from_switch_stays_unassigned():
    """SPEC-014/R-1: nothing is assigned by similarity; what has no identical row stays unassigned."""
    r = rows(JA, JC)
    slots = [(0x100, JA), (0x108, JB), (0x110, JC)]                 # JB exists only in Android: never matched by similarity
    got = align.align(slots, r)
    assert got[1] is None and got[0] == (0, "exact") and got[2] == (1, "exact")


def test_second_pass_places_a_text_that_is_out_of_order():
    r = rows(JA, JB, JC, JD)
    slots = [(0x100, JB), (0x108, JA), (0x110, JC), (0x118, JD)]    # the first two are swapped in this build
    got = align.align(slots, r)
    assert [g for g, _ in got] == [1, 0, 2, 3]


def test_slots_and_literals_of_a_library():
    lib, info = make_library(strings=[JA.encode(), b"ascii only", ("\n" + JB + JC).encode()[1:]], relocs=[(0, 0), (1, 1)])
    e = Elf(lib)
    slots = align.android_slots(e, limit=0x2000)
    assert slots == [(info["slots"][0], JA)]                       # the ASCII string is not script text
    lits = align.android_literals(e, lo=0x1000, limit=0x2000)       # the third string has no pointer: the code uses it directly
    assert [t for _, t in lits] == [JB + JC]


def test_align_library_reports_the_unmapped():
    lib, info = make_library(strings=[JA.encode(), JB.encode()], relocs=[(0, 0), (1, 1)])
    e = Elf(lib)
    res = align.align_library(e, rows(JA))
    assert res.rows == {info["slots"][0]: 0}
    assert res.unmapped == [info["slots"][1]]
    assert res.how["exact"] == 1
