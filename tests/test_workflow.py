"""SPEC-008: the translator's workflow (extract, validate, sync, newlang)."""

import json

import pytest

from riviera import packs, ui, workflow


def test_units_are_unique_strings_with_fingerprints(dump):
    """SPEC-008/R-10"""
    from riviera.nso import Nso, read_rows
    units = workflow.units_of(read_rows(Nso(dump.exefs / "main")))
    assert len(units) == 5
    u = units[packs.fingerprint("V(112b_0000)How are you today,V(112b_0001)friend?")]
    assert u["en"] == ["How are you today", "friend?"] and u["tags"] == ["V(112b_0000)", "V(112b_0001)"] and u["rows"] == 1


def test_extract_puts_the_english_next_to_the_translation(project, langs):
    """SPEC-008/R-10"""
    assert workflow.extract(project, "xx", "xx", ui) == 0
    rows = list(packs.read_jsonl(project.switch_work / "lang" / "xx" / "units.jsonl"))
    assert len(rows) == 5 and all(r["t"] for r in rows)
    assert {r["en"][0] for r in rows} >= {"Hello", "Yes", "No"}


def test_a_new_language_starts_empty_and_is_filled_by_sync(project, langs):
    """SPEC-008/R-11"""
    assert workflow.newlang(project, "fr", "Français", "xx", ui) == 0
    folder = project.langs / "fr"
    meta = json.loads((folder / "lang.json").read_text(encoding="utf-8"))
    assert meta["code"] == "fr" and meta["mod_name"] == "Riviera_FR" and "font" not in meta
    workflow.extract(project, "xx", "fr", ui)
    work = project.switch_work / "lang" / "fr" / "units.jsonl"
    rows = list(packs.read_jsonl(work))
    assert all(r["t"] is None for r in rows)
    for r in rows:
        if r["en"] == ["Hello"]:
            r["t"] = ["Bonjour"]
    packs.write_jsonl(work, rows)
    workflow.sync(project, "fr", ui)
    assert packs.get_pack(project.langs, "fr").text() == {packs.fingerprint("Hello"): ["Bonjour"]}


def test_sync_refuses_a_wrong_number_of_segments(project, langs):
    """SPEC-008/R-11"""
    workflow.newlang(project, "fr", "Français", "xx", ui)
    workflow.extract(project, "xx", "fr", ui)
    work = project.switch_work / "lang" / "fr" / "units.jsonl"
    rows = list(packs.read_jsonl(work))
    for r in rows:
        if len(r["en"]) == 2:
            r["t"] = ["only one"]
    packs.write_jsonl(work, rows)
    with pytest.raises(packs.PackError, match="2 segments"):
        workflow.sync(project, "fr", ui)


def test_sync_keeps_entries_the_current_dump_does_not_have(project, langs):
    """SPEC-005/R-8: translating from one dump never deletes the work done against another."""
    workflow.newlang(project, "fr", "Français", "xx", ui)
    pack = packs.get_pack(project.langs, "fr")
    packs.write_jsonl(pack.path / "text.jsonl", [{"k": "f" * 16, "t": ["from another version"]}])
    workflow.extract(project, "xx", "fr", ui)
    workflow.sync(project, "fr", ui)
    assert "f" * 16 in packs.get_pack(project.langs, "fr").text()


def test_validate_passes_a_good_pack_and_reports_a_bad_one(project, langs, capsys):
    """SPEC-008/R-12"""
    assert workflow.validate(project, "xx", ui) == 0
    pack = langs.pack
    text = pack.text()
    text[packs.fingerprint("Press the B1 Button")] = ["Pulsa el botón"]                      # lost its marker
    packs.write_jsonl(pack.path / "text.jsonl", ({"k": k, "t": t} for k, t in sorted(text.items())))
    assert workflow.validate(project, "xx", ui) == 1
    assert "markers" in capsys.readouterr().out


def test_validate_reports_characters_the_pack_does_not_allow(project, langs, capsys):
    """SPEC-008/R-13"""
    pack = langs.pack
    text = pack.text()
    text[packs.fingerprint("Hello")] = ["Hóla ñ ï"]
    packs.write_jsonl(pack.path / "text.jsonl", ({"k": k, "t": t} for k, t in sorted(text.items())))
    assert workflow.validate(project, "xx", ui) == 1
    assert "not allowed" in capsys.readouterr().out


def test_validate_applies_the_forbidden_patterns_of_the_pack(project, langs, capsys):
    """SPEC-008/R-13"""
    meta = json.loads((langs.pack.path / "lang.json").read_text(encoding="utf-8"))
    meta["validation"]["forbidden"] = [{"pattern": r"\bHola\b", "message": "say Buenas"}]
    (langs.pack.path / "lang.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    assert workflow.validate(project, "xx", ui) == 1
    assert "say Buenas" in capsys.readouterr().out


def test_sync_refuses_text_that_looks_like_the_games_own(project, langs):
    """SPEC-005/R-6"""
    workflow.newlang(project, "fr", "Français", "xx", ui)
    workflow.extract(project, "xx", "fr", ui)
    work = project.switch_work / "lang" / "fr" / "units.jsonl"
    rows = list(packs.read_jsonl(work))
    rows[0]["t"] = ["日本語"] * len(rows[0]["en"])
    packs.write_jsonl(work, rows)
    with pytest.raises(packs.PackError, match="looks like the game's own"):
        workflow.sync(project, "fr", ui)
