"""SPEC-004, SPEC-005: language packs, and keeping the game's text out of the repository."""

import json
import re
from pathlib import Path

import pytest

import synth
from riviera import packs

REPO = Path(__file__).resolve().parent.parent
LANGS = REPO / "langs"


def test_fingerprint_is_the_first_16_hex_digits_of_sha1():
    """SPEC-005/R-1"""
    assert packs.fingerprint("abc") == "a9993e364706816a"
    assert packs.fingerprint("abc") == packs.fingerprint("abc")
    assert len(packs.fingerprint("x" * 10000)) == 16                     # fixed length whatever the input


def test_discover_lists_packs_sorted(tmp_path):
    """SPEC-004/R-1"""
    synth.make_lang(tmp_path, "zz", {}, images=False)
    synth.make_lang(tmp_path, "aa", {}, images=False)
    (tmp_path / "not-a-pack").mkdir()
    assert [p.code for p in packs.discover(tmp_path)] == ["aa", "zz"]


def test_mandatory_fields(tmp_path):
    """SPEC-004/R-2"""
    d = tmp_path / "xx"
    d.mkdir()
    (d / "lang.json").write_text(json.dumps({"code": "xx", "name": "X"}))
    with pytest.raises(packs.PackError, match="mod_name"):
        packs.load_pack(d)


@pytest.mark.parametrize("meta,msg", [({"code": "XX"}, "language code"), ({"code": "e"}, "language code"),
                                      ({"mod_name": "a/b"}, "mod_name"), ({"mod_name": ".."}, "mod_name")])
def test_bad_codes_and_names(tmp_path, meta, msg):
    """SPEC-004/R-3"""
    d = tmp_path / "xx"
    d.mkdir()
    (d / "lang.json").write_text(json.dumps({"code": "xx", "name": "X", "mod_name": "X", **meta}))
    with pytest.raises(packs.PackError, match=msg):
        packs.load_pack(d)


def test_unknown_pack(tmp_path):
    """SPEC-004/R-1"""
    synth.make_lang(tmp_path, "aa", {}, images=False)
    with pytest.raises(packs.PackError, match="available: aa"):
        packs.get_pack(tmp_path, "bb")


def test_optional_fields_have_defaults(tmp_path):
    """SPEC-004/R-4"""
    d = tmp_path / "xx"
    d.mkdir()
    (d / "lang.json").write_text(json.dumps({"code": "xx", "name": "X", "mod_name": "X"}))
    p = packs.load_pack(d)
    assert p.platform("switch") == {} and not p.supports("switch") and not p.needs_font_patch and p.text() == {}


def test_source_text_scan_catches_the_games_script(tmp_path):
    """SPEC-005/R-4: Japanese, Korean, Chinese and full-width forms are the game's text."""
    f = tmp_path / "text.jsonl"
    for bad in ("日本語", "はい", "ＡＢ", "한글", "？"):
        f.write_text(json.dumps({"k": "0" * 16, "t": [bad]}, ensure_ascii=False), encoding="utf-8")
        assert packs.source_text_problems(tmp_path), bad


def test_source_text_scan_lets_the_known_markers_through(tmp_path):
    """SPEC-005/R-4: bullets and the sweat-drop symbol are in the translations because the game writes them in its English."""
    (tmp_path / "text.jsonl").write_text(json.dumps({"k": "0" * 16, "t": ["・uno ￥ ¡Qué!"]}, ensure_ascii=False), encoding="utf-8")
    assert packs.source_text_problems(tmp_path) == []


def test_text_is_keyed_by_fingerprint(langs):
    """SPEC-005/R-2"""
    t = langs.pack.text()
    assert t[packs.fingerprint("Hello")] == ["Hola"]


# ---- the packs that ship with the repository -----------------------------------------------------------------------------

def test_shipped_packs_carry_no_game_text():
    """SPEC-005/R-4: this is the check that keeps the repository redistributable."""
    assert packs.source_text_problems(LANGS) == []


def test_shipped_packs_load():
    """SPEC-004/R-1"""
    found = {p.code: p for p in packs.discover(LANGS)}
    assert {"es", "en"} <= set(found)
    assert found["es"].supports("switch") and found["es"].supports("android") and found["es"].needs_font_patch
    assert found["en"].supports("android") and not found["en"].supports("switch")


def test_shipped_script_entries_are_well_formed():
    """SPEC-005/R-2, R-3"""
    seen = set()
    for o in packs.read_jsonl(LANGS / "es" / "text.jsonl"):
        assert re.fullmatch(r"[0-9a-f]{16}", o["k"]), o
        assert o["k"] not in seen
        seen.add(o["k"])
        assert isinstance(o["t"], list) and o["t"] and all(isinstance(s, str) for s in o["t"]), o
        if o["k"] != packs.fingerprint(""):                               # the empty string translates to itself
            assert all(s for s in o["t"]), o
    assert len(seen) > 11000


@pytest.mark.parametrize("path", sorted(LANGS.glob("*/android/*.jsonl")), ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_shipped_android_entries_are_well_formed(path):
    """SPEC-005/R-2"""
    for o in packs.read_jsonl(path):
        assert re.fullmatch(r"[0-9a-f]{16}", o["k"]), o
        assert ("t" in o) != ("ref" in o), o                              # its own text, or a reference to the Switch script
        assert re.fullmatch(r"[0-9a-f]{16}", o.get("ref", "0" * 16)), o
        assert isinstance(o.get("t", ""), (str, list)), o


def test_the_image_manifest_matches_its_files():
    """SPEC-003/R-5, R-8"""
    base = LANGS / "es" / "images"
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    n = 0
    for container, pkgs in manifest["containers"].items():
        for package, entries in pkgs.items():
            for name, spec in entries.items():
                n += 1
                assert re.fullmatch(r"[0-9a-f]{40}", spec["base"]), (package, name)
                if spec["kind"] == "full":
                    assert (base / spec["file"]).is_file(), spec
                else:
                    assert spec["kind"] == "delta" and (base / spec["overlay"]).is_file() and (base / spec["mask"]).is_file(), spec
    assert n == 200


def test_the_spanish_pack_ships_its_documentation():
    """SPEC-004/R-5"""
    assert (LANGS / "es" / "GLOSSARY.md").is_file() and (LANGS / "es" / "lang.json").is_file()


def test_the_games_text_and_the_generated_mods_stay_out_of_git():
    """SPEC-005/R-7"""
    ignored = {line.strip() for line in (REPO / ".gitignore").read_text().splitlines()}
    for must in ("work/", "build/", "*.xci", "*.nsp", "*.apk", "*.keys", "rpl.config.json"):
        assert must in ignored, must
