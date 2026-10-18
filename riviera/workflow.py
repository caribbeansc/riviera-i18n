"""The translator's workflow: look at the strings of your dump, translate, check, publish.

The game's own text only ever exists under ``work/`` on your machine (it is in ``.gitignore``). What goes into ``langs/`` is
the fingerprint of every string plus your translation of it, nothing else (SPEC-005).

    python rpl.py newlang fr --name "Français" --like es   # a new, empty pack
    python rpl.py extract fr                               # work/switch/lang/fr/units.jsonl: English next to your translation
    # ... edit the "t" lists in that file ...
    python rpl.py validate fr
    python rpl.py sync fr                                  # work/ -> langs/fr/text.jsonl (keys and translations only)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import packs, segments
from . import validate as rules
from .config import ConfigError, Project
from .nso import Nso, read_rows


def units_of(rows) -> dict:
    """``{fingerprint: unit}`` for every distinct string of the script, in order of appearance.

    A unit has ``en`` (the readable segments), ``tags`` (the voice / colour tag of each segment), the ``block`` and ``row`` where
    it first appears and the number of rows that use it.
    """
    out: dict[str, dict] = {}
    for r in rows:
        k = packs.fingerprint(r["en"])
        u = out.get(k)
        if u is None:
            segs = segments.split_segments(r["en"])
            u = out[k] = {"k": k, "block": r["block"], "row": r["row"], "rows": 0,
                          "tags": [p for _, p, _ in segs], "en": [segments.disp(t) for _, _, t in segs]}
        u["rows"] += 1
    return out


def _dump_units(project: Project) -> dict:
    exefs, _ = project.require_switch()
    return units_of(read_rows(Nso(exefs / "main")))


def lang_work_dir(project: Project, code: str) -> Path:
    return project.switch_work / "lang" / code


def extract(project: Project, like: str, lang: str | None, ui) -> int:
    """Write ``work/switch/lang/<code>/units.jsonl``: the strings in the scope of the ``like`` pack, with ``lang``'s translations."""
    reference = packs.get_pack(project.langs, like)
    scope = reference.text()
    target = packs.get_pack(project.langs, lang) if lang else reference
    done = target.text()
    units = _dump_units(project)
    out = lang_work_dir(project, target.code)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, u in units.items():
        if k not in scope:
            continue
        rows.append({**u, "t": done.get(k)})
    packs.write_jsonl(out / "units.jsonl", rows)
    missing = [k for k in scope if k not in units]
    pending = sum(1 for r in rows if not r["t"])
    ui.ok(f"{len(rows)} strings in scope -> {out / 'units.jsonl'}   ({pending} without a translation)")
    if missing:
        ui.warn(f"{len(missing)} strings of the {like} pack are not in your dump (another version of the game?)")
    return 0


def newlang(project: Project, code: str, name: str, like: str, ui) -> int:
    reference = packs.get_pack(project.langs, like)
    if not packs.CODE.match(code):
        raise packs.PackError(f"{code!r} is not a language code (examples: fr, pt-br)")
    folder = project.langs / code
    if folder.exists():
        raise packs.PackError(f"{folder} already exists")
    meta = json.loads(json.dumps(reference.meta))
    meta.update(code=code, name=name, english_name=name, mod_name="Riviera_" + re.sub(r"[^A-Za-z0-9]", "", code).upper())
    meta.pop("validation", None)
    meta.pop("font", None)
    folder.mkdir(parents=True)
    (folder / "lang.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "text.jsonl").write_text("", encoding="utf-8")
    ui.ok(f"created {folder}")
    ui.info("next: edit langs/%s/lang.json (add font.accents and validation.extra_chars if your language needs letters the font lacks),"
            " then `python rpl.py extract %s`" % (code, code))
    return 0


def sync(project: Project, lang: str, ui) -> int:
    """Move the translations of ``work/.../units.jsonl`` into ``langs/<lang>/text.jsonl``, keeping the ones already there."""
    pack = packs.get_pack(project.langs, lang)
    src = lang_work_dir(project, lang) / "units.jsonl"
    if not src.is_file():
        raise ConfigError(f"{src} does not exist: run `python rpl.py extract {lang}` first")
    merged = dict(pack.text())            # keeps entries the current dump does not contain (another version of the game)
    n = 0
    for u in packs.read_jsonl(src):
        t = u.get("t")
        if not t:
            continue
        if not isinstance(t, list) or len(t) != len(u["en"]):
            raise packs.PackError(f"{u['k']}: expected {len(u['en'])} segments")
        merged[u["k"]] = t
        n += 1
    packs.write_jsonl(pack.path / "text.jsonl", ({"k": k, "t": merged[k]} for k in sorted(merged)))
    leaks = packs.source_text_problems(pack.path)
    if leaks:
        raise packs.PackError("the pack would contain text that looks like the game's own:\n  " + "\n  ".join(leaks[:5]))
    ui.ok(f"{n} translations merged; {len(merged)} strings in langs/{lang}/text.jsonl")
    return 0


def _forbidden(pack: packs.LangPack):
    out = []
    for item in pack.meta.get("validation", {}).get("forbidden", []):
        out.append((re.compile(item["pattern"]), item.get("message", f"matches {item['pattern']}")))
    return out


def validate_pack(project: Project, pack: packs.LangPack, units: dict | None, ui):
    """Check a pack. With ``units`` (from your dump) the markers and segment counts are checked against the game too."""
    errors, warns = [], []
    allowed = pack.meta.get("validation", {}).get("extra_chars", "")
    forbidden = _forbidden(pack)
    text = pack.text()
    if not text and (pack.path / "text.jsonl").exists() and (pack.path / "text.jsonl").stat().st_size:
        errors.append("text.jsonl could not be read")
    for k, t in text.items():
        if not re.fullmatch(r"[0-9a-f]{16}", k):
            errors.append(f"{k}: not a fingerprint")
        elif not isinstance(t, list) or not all(isinstance(s, str) for s in t):
            errors.append(f"{k}: the translation must be a list of strings")
        else:
            if allowed:
                # a character the game's own English uses (a symbol, an invented alphabet) is fine in the translation of that string
                here = allowed + "".join(units[k]["en"]) if units is not None and k in units else allowed
                odd = rules.unusual_chars(t, here)
                if odd and units is not None:
                    errors.append(f"{k}: characters {odd!r} are not allowed (validation.extra_chars)")
                elif odd:
                    warns.append(f"{k}: characters {odd!r} are not in validation.extra_chars (compared with your dump they may be fine)")
            for s in t:
                for pattern, message in forbidden:
                    if pattern.search(s):
                        errors.append(f"{k}: {message}: {s!r}")
    for line in packs.source_text_problems(pack.path):
        errors.append(f"source text? {line}")
    checked = 0
    if units is not None:
        for k, t in text.items():
            u = units.get(k)
            if u is None:
                continue
            checked += 1
            e, w = rules.check_entry(k, u["en"], t, [])
            errors += e
            warns += w
    return errors, warns, checked


def validate(project: Project, lang: str, ui) -> int:
    pack = packs.get_pack(project.langs, lang)
    units = _dump_units(project) if project.has_switch() else None
    ui.step(f"Checking the {pack.name} pack" + ("" if units is not None else " (no dump configured: the checks against the game are skipped)"))
    errors, warns, checked = validate_pack(project, pack, units, ui)
    if units is not None:
        ui.info(f"{checked} strings compared with your dump")
    for w in warns[:40]:
        ui.warn(w)
    for e in errors[:60]:
        ui.fail(e)
    if len(errors) > 60:
        ui.info(f"... and {len(errors) - 60} more errors")
    if units is not None and pack.supports("switch"):
        from .switch import build as sw_build
        ui.info("Checking that everything fits its box (builds the executable patch, nothing is written to the game)")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = sw_build.build(project, pack, out_dir=tmp, with_romfs=False, say=lambda m: None)
        s = report.summary
        ui.kv("overflow", f"{s['overflow']} rows do not fit their box", status="ok" if not s["overflow"] else "warn")
        for o in report.overflow[:20]:
            ui.detail(f"block {o['block']} row {o['row']}: {o['lines']} lines (max {o['max']})  {o['text']}")
        if s["no_room"] or s["verification_failures"]:
            errors.append("the executable patch failed its own verification")
        if s.get("missing_glyphs") and pack.needs_font_patch:
            ui.kv("no glyph", "".join(s["missing_glyphs"]), status="warn")
    ui.kv("result", f"{len(errors)} errors, {len(warns)} warnings", status="ok" if not errors else "fail")
    return 1 if errors else 0
