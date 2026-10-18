"""SPEC-009: the line composer."""

from riviera import compose, segments


class Fake:
    """Metrics where every letter is 10 wide and a space 4: easy to reason about."""
    def glyph(self, ch):
        return 4 if ch in " 　" else 10

    def line(self, text):
        return sum(self.glyph(c) for c in text)


M = Fake()


def test_wrap_uses_the_fewest_lines():
    """SPEC-009/R-1"""
    lines = compose.wrap_units("aaa bbb ccc ddd eee fff", 100, M)
    assert len(lines) == 2                                              # 3 words fit a 100-wide line: 2 lines is the minimum
    assert " ".join(lines) == "aaa bbb ccc ddd eee fff"


def test_wrap_balances_the_lines():
    """SPEC-009/R-2: the cap is tightened to the smallest one that still gives the same number of lines, so the last
    lines come out even (3-3 instead of 4-2)."""
    text = "xxxxxxxx yy yy yy yy yy yy"                                  # one wide word, then six short ones
    assert [len(l.split()) for l in compose.wrap_units(text, 100, M)] == [1, 3, 3]


def test_a_word_wider_than_the_box_gets_its_own_line():
    """SPEC-009/R-1"""
    lines = compose.wrap_units("a verylongword b", 50, M)
    assert "verylongword" in lines


def test_one_line_stays_one_line():
    """SPEC-009/R-1"""
    assert compose.wrap_units("hello world", 1000, M) == ["hello world"]


def test_chains_follow_when_the_english_starts_with_a_space():
    """SPEC-009/R-3: ", \\nhas been added" continues the sentence; a segment with a tag opens a new one."""
    segs = segments.split_segments("Hard,\n has been added,c1Next page")
    chains = compose.seg_chains([(a, b, c if i != 1 else " " + c) for i, (a, b, c) in enumerate(segs)])
    assert chains == [[0, 1], [2]]
    assert compose.seg_chains(segments.split_segments("one,two")) == [[0], [1]]


def test_ui_cap_prefers_the_english_lines():
    """SPEC-009/R-4: a two-line English message is composed in two lines at about the English width, not in one long line."""
    words = "Do you want to overwrite this data? Saved data cannot be recovered".split()
    n_en, w_en = 2, 400
    cap = compose.ui_cap(words, n_en, w_en, 1904, M)
    assert cap < 1904
    assert len(compose.wrap_words(words, cap, M)) <= n_en


def test_ui_cap_falls_back_to_the_family_cap():
    """SPEC-009/R-4"""
    words = ["x" * 30] * 12
    assert compose.ui_cap(words, 2, 200, 900, M) == 900


def test_has_voice_and_row_level():
    """SPEC-009/R-5: dialogue and voiced lines are composed segment by segment; the rest as a whole row."""
    assert compose.has_voice("V(1)Hello") and not compose.has_voice("Hello")
    assert not compose.row_level({"block": 12, "en": "Hello"})            # dialogue block
    assert not compose.row_level({"block": 5, "en": "V(1)Hello"})
    assert compose.row_level({"block": 5, "en": "Hello"})
    assert not compose.row_level({"block": 33, "en": "Name"})


def test_bullets_are_detected():
    """SPEC-009/R-6"""
    assert compose.is_bullets(["・one", "・two"]) and not compose.is_bullets(["one", "・two"])


def test_compose_row_keeps_markers_and_line_breaks():
    """SPEC-009/R-7"""
    rows = [{"block": 5, "row": 0, "en": "Press the B1 Button", "slots": [0, 0, 0, 0]},
            {"block": 5, "row": 1, "en": "Yes", "slots": [0, 0, 0, 0]}]
    caps = compose.block_caps(rows, M)
    raw, n, mx, cap, widest, enc = compose.compose_row(rows[0], ["Pulsa el botón B1"], caps, M)
    assert "B1" in raw and "Pulsa" in raw
    assert n <= mx and widest <= cap
    assert "," not in raw and ";" not in raw                            # one line: no break, and no stray separator


def test_compose_row_breaks_a_long_line_into_the_english_lines():
    """SPEC-009/R-7"""
    en = "First line of the help;second line of the help"
    rows = [{"block": 37, "row": 0, "en": en, "slots": [0, 0, 0, 0]}]
    caps = compose.block_caps(rows, M)
    raw, n, mx, cap, widest, enc = compose.compose_row(rows[0], ["Esta es la primera línea y la segunda"], caps, M)
    assert mx == 2 and n == 2 and raw.count(";") == 1


def test_a_chained_segment_does_not_end_in_a_comma():
    """SPEC-009/R-8: the separating comma is drawn by the engine, so a segment that continues cannot end in one (",,")."""
    en = "Hard, \nhas been added"
    rows = [{"block": 37, "row": 0, "en": en, "slots": [0, 0, 0, 0]}]
    caps = compose.block_caps(rows, M)
    raw, *_ = compose.compose_row(rows[0], ["Difícil,", "se ha agregado"], caps, M)
    assert ",," not in raw and "，," not in raw
