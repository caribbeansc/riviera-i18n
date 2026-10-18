"""Hygiene of the Android parts of the language packs in the repository (SPEC-014, SPEC-016): well-formed files, no game text, and
every picture the manifest names. The checks that need the game's own files are marked ``game``."""

import json
import re
from pathlib import Path

import pytest

from riviera import images as swimages
from riviera import packs

LANGS = Path(__file__).resolve().parent.parent / "langs"
PACKS = sorted(d for d in LANGS.iterdir() if (d / "android").is_dir()) if LANGS.is_dir() else []
HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
KINDS = {"full", "delta", "layer"}


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def pack_ids():
    return [p.name for p in PACKS]


@pytest.mark.parametrize("code", pack_ids())
def test_the_android_text_is_well_formed(code):
    """SPEC-014/R-6: keys, segments, references and flags are as the format says, and the text carries no markers (the composer breaks lines)."""
    entries = rows(LANGS / code / "android" / "text.jsonl")
    assert entries, "an Android pack has text"
    seen = set()
    for o in entries:
        assert HEX16.match(o["k"]) and o["k"] not in seen, o["k"]
        seen.add(o["k"])
        assert ("t" in o) != ("ref" in o), f"{o['k']}: text or reference, not both"
        assert set(o) <= {"k", "t", "ref", "cap", "lit", "force"}, o
        if "ref" in o:
            assert HEX16.match(o["ref"]) and "lit" not in o
            continue
        assert isinstance(o["t"], list) and o["t"]
        for item in o["t"]:
            if isinstance(item, dict):
                assert set(item) <= {"ref", "seg"} and HEX16.match(item["ref"]) and isinstance(item.get("seg", 0), int)
                continue
            assert isinstance(item, str) and item.strip()
            assert not re.search(r"V\(|\bc\d\b", item), f"{o['k']}: a marker in the text"
            if not o.get("lit"):
                assert ";" not in item and "\n" not in item, f"{o['k']}: a line break (the composer makes them)"
        if "cap" in o:
            assert isinstance(o["cap"], int) and 100 <= o["cap"] <= 3000
    java = rows(LANGS / code / "android" / "java.jsonl")
    assert all(HEX16.match(o["k"]) and isinstance(o["t"], str) and set(o) == {"k", "t"} for o in java)


@pytest.mark.parametrize("code", pack_ids())
def test_the_android_pack_holds_no_script_of_the_game(code):
    """SPEC-014/R-9: no Japanese (or other source characters) in the Android part of a pack: translations and references only."""
    assert packs.source_text_problems(LANGS / code / "android") == []


def test_every_language_translates_the_same_android_strings():
    """The languages of the repository cover the same strings of the Android app."""
    keys = {code: {o["k"] for o in rows(LANGS / code / "android" / "text.jsonl")} for code in pack_ids()}
    java = {code: {o["k"] for o in rows(LANGS / code / "android" / "java.jsonl")} for code in pack_ids()}
    first = next(iter(keys.values()), set())
    assert all(k == first for k in keys.values()), "the languages do not have the same Android strings"
    assert len({frozenset(j) for j in java.values()}) <= 1


@pytest.mark.parametrize("code", [c for c in pack_ids() if (LANGS / c / "android" / "images" / swimages.MANIFEST).is_file()])
def test_the_files_of_the_pictures_are_exactly_the_manifest_files(code):
    """SPEC-016/R-11: the manifest only uses full, delta and layer, names files that exist, and the folder has no other file."""
    folder = LANGS / code / "android" / "images"
    manifest = json.loads((folder / swimages.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["format"] == 1 and set(manifest["containers"]) == {"android"}
    named = set()
    for package, entries in manifest["containers"]["android"].items():
        assert package.startswith("data/")
        for key, spec in entries.items():
            assert spec["kind"] in KINDS, f"{package}/{key}"
            assert key == key.lower()
            if spec.get("base"):
                assert HEX40.match(spec["base"])
            if spec["kind"] == "full":
                named.add(spec["file"])
            elif spec["kind"] == "delta":
                named |= {spec["overlay"], spec["mask"]}
            else:
                assert spec["size"] and spec["ops"]
                for op in spec["ops"]:
                    assert op["op"] in ("layer", "copy", "erase_enclosed")
                    if op["op"] == "layer":
                        named.add(op["file"])
                    elif op["op"] == "copy":
                        assert len(op["box"]) == 4 and len(op["to"]) == 2
                if "bleed" in spec:
                    assert len(spec["bleed"]) == 3
                assert spec.get("encode", "exact") in ("exact", "plain")
    present = {f.name for f in folder.iterdir() if f.name != swimages.MANIFEST}
    assert named == present, f"listed but missing: {sorted(named - present)}; present but not listed: {sorted(present - named)}"


@pytest.mark.parametrize("code", [c for c in pack_ids() if (LANGS / c / "android" / "images" / swimages.MANIFEST).is_file()])
def test_no_picture_of_the_pack_traces_the_japanese(code):
    """SPEC-016/R-12: a delta of an Android picture has a solid rectangular mask (nothing traces the glyphs of a label that was replaced)."""
    from PIL import Image
    folder = LANGS / code / "android" / "images"
    manifest = json.loads((folder / swimages.MANIFEST).read_text(encoding="utf-8"))
    for package, entries in manifest["containers"]["android"].items():
        for key, spec in entries.items():
            if spec["kind"] != "delta":
                continue
            mask = Image.open(folder / spec["mask"]).convert("L")
            box = mask.getbbox()
            area = (box[2] - box[0]) * (box[3] - box[1]) if box else 0
            assert sum(1 for v in mask.tobytes() if v) == area, f"{package}/{key}: the mask is not a solid rectangle"


# ---------------------------------------------------- with the game's files --

@pytest.mark.game
@pytest.mark.parametrize("code", pack_ids())
def test_no_line_of_the_official_script_is_in_the_android_pack(code):
    """SPEC-014/R-9: no string of 20 characters or more of the Android text equals a string of the official script; the references resolve."""
    from riviera import config, workflow
    from riviera import nso as nsomod
    from riviera.android import text
    proj = config.load()
    if not proj.has_switch():
        pytest.skip("no Switch dump configured (python rpl.py setup)")
    units = workflow.units_of(nsomod.read_rows(nsomod.Nso(proj.exefs / "main")))
    official = {re.sub(r"\s+", " ", s.strip().lower()) for u in units.values() for s in u["en"]}
    texts, lits = text.read_android_text(LANGS / code / "android" / "text.jsonl")
    for k, o in {**texts, **lits}.items():
        for item in o.get("t", []):
            if isinstance(item, str) and len(item) >= 20:
                assert re.sub(r"\s+", " ", item.strip().lower()) not in official, f"{code}: the entry {k} copies the official script: {item!r}"
    text.resolve_entries({**texts, **lits}, text.donor_units(nsomod.read_rows(nsomod.Nso(proj.exefs / "main"))))
