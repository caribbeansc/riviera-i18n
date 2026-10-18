"""SPEC-002: segments of a string."""

import pytest

from riviera import segments as S


def test_segments_join_back():
    """SPEC-002/R-6"""
    for raw in ["Hello", "V(112b_0000)How are you today,V(112b_0001)friend?", "c1Press the B1 Button, \nto go on",
                "V(1)one;two;V(2)three", "text,c1more,V(7)x"]:
        segs = S.split_segments(raw)
        assert "".join(sep + prefix + text for sep, prefix, text in segs) == raw


def test_every_comma_and_voice_tag_opens_a_segment():
    """SPEC-002/R-6"""
    segs = S.split_segments("V(a)one,V(b)two,three")
    assert [(p, t) for _, p, t in segs] == [("V(a)", "one"), ("V(b)", "two"), ("", "three")]
    assert segs[1][0] == "," and segs[0][0] == ""


def test_colour_tag_is_a_prefix():
    """SPEC-002/R-6"""
    assert S.split_segments("c1Hello")[0][1:] == ("c1", "Hello")


def test_disp_makes_text_readable():
    """SPEC-002/R-7"""
    assert S.disp("Ｈｅｌｌｏ　ｗｏｒｌｄ＿") == "Hello world…"
    assert S.disp("line one;line two\nline three") == "line one line two line three"
    assert S.disp("It’s a−b") == "It's a-b"


@pytest.mark.parametrize("block,en,expected", [
    (12, "V(1)anything", True), (25, "A place", True), (10, "Yes", True), (36, "A short name", False),
    (36, "A description\nwith a break;", True), (5, "Menu", False),
])
def test_wanted_narrative(block, en, expected):
    """SPEC-002/R-8"""
    assert S.wanted(block, en) is expected


def test_blocks_cover_the_whole_table():
    """SPEC-002/R-8"""
    allb = set(S.STORY) | set(S.DESC) | set(S.CHOICES) | set(S.ITEMS) | set(S.UI) | set(S.NAMES)
    assert allb == set(range(41))
