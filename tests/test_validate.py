"""SPEC-008: the translation validator."""

import re

from riviera import validate as V


def check(en, t, **kw):
    return V.check_entry("k", en, t, **kw)


def test_a_good_translation_has_no_errors():
    """SPEC-008/R-1"""
    assert check(["Press the B1 Button"], ["Pulsa el botón B1"]) == ([], [])


def test_the_number_of_segments_must_match():
    """SPEC-008/R-2"""
    errors, _ = check(["one", "two"], ["uno"])
    assert errors and "1 segments, expected 2" in errors[0]
    assert check(["one"], "uno")[0]


def test_markers_must_survive():
    """SPEC-008/R-3"""
    assert check(["Raises STR by p1"], ["Sube la FUE"])[0]
    assert not check(["Raises STR by p1"], ["Sube la FUE en p1"])[0]
    assert check(["Press B1"], ["Pulsa B2"])[0]
    assert check(["75 %d"], ["75"])[0]


def test_silences_are_copied():
    """SPEC-008/R-4"""
    assert check(["…"], ["..."])[0]
    assert not check(["…"], ["…"])[0]


def test_forbidden_characters():
    """SPEC-008/R-5: the composer breaks the lines, so ; | tabs and breaks are refused."""
    for bad in ("uno;dos", "uno|dos", "uno\ndos", "uno\tdos"):
        assert check(["one two"], [bad])[0], bad


def test_game_text_in_a_translation_is_an_error():
    """SPEC-008/R-6"""
    assert check(["Hello"], ["日本語"])[0]
    assert check(["Hello"], ["Ｈｏｌａ"])[0]
    assert not check(["Duplicate ACC for あ turns"], ["Duplica ACC por あ turnos"])[0]    # the English has it too


def test_empty_segments_are_errors():
    """SPEC-008/R-2"""
    assert check(["Hello"], [""])[0]


def test_warnings_are_judgement_calls():
    """SPEC-008/R-7"""
    _, warns = check(["Short"], ["Una traducción muchísimo más larga que el original sin necesidad alguna"])
    assert any("long" in w for w in warns)
    _, warns = check(["Are you sure about this?"], ["Estás seguro de esto?"])
    assert any("¿" in w for w in warns)
    _, warns = check(["Hello there"], ["Hola  allí"])
    assert any("spaces" in w for w in warns)


def test_forbidden_patterns_of_a_pack():
    """SPEC-008/R-8"""
    rule = [(re.compile(r"\bMagos\b"), "use Magi")]
    assert check(["The Magi"], ["Los Magos"], extra_forbidden=rule)[0]
    assert not check(["The Magi"], ["Los Magi"], extra_forbidden=rule)[0]


def test_unusual_characters():
    """SPEC-008/R-9"""
    assert V.unusual_chars(["¿Qué?", "ñandú"], "áéíóúñ¿") == ""
    assert V.unusual_chars(["naïve"], "áéíóúñ¿") == "ï"
