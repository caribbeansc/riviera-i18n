"""Language packs: what a translation is made of, and how this repository keeps game text out of them.

A language is a folder under ``langs/``::

    langs/<code>/
    ├── lang.json            metadata and per-platform layout parameters
    ├── text.jsonl           the script: one line per string, {"k": fingerprint, "t": [segments]}
    ├── images/              the artwork the translation draws or changes (see riviera.images)
    ├── android/             strings and artwork that exist only in the Android app
    └── GLOSSARY.md          optional, human-facing terminology rules

A translation is stored as the **fingerprint** of the original string plus the translated
segments, never the original: ``k`` is the first 16 hex digits of the SHA-1 of the string as
the game stores it. It identifies a string you already have; it does not carry it. See
docs/specs/SPEC-005-translation-keys.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

CODE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})*$")

#: Characters that look like game text (CJK, kana, full-width forms) but are legitimate inside a translation, because the game
#: itself writes them into its English: ``・`` marks the bullets of the list-style descriptions, ``￥`` is the sweat-drop symbol
#: the engine draws, ``あ`` is a placeholder the English script uses for the number of turns and ``、`` appears once in an
#: inscription written in an invented alphabet.
ALLOWED_SOURCE_CHARS = frozenset("\u30fb\uffe5\u3042\u3001")

#: Ranges that must not appear in a pack (SPEC-005/R-4): CJK punctuation, kana, ideographs, Hangul and full-width forms.
SOURCE_RANGES = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\uff00-\uffef]")


class PackError(Exception):
    """A language pack is missing, malformed or contains something it must not."""


def fingerprint(raw: str) -> str:
    """Stable key of a string of the script: the first 16 hex digits of the SHA-1 of its UTF-8 bytes."""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def read_jsonl(path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise PackError(f"{path}:{n}: not valid JSON ({e})") from None


def write_jsonl(path, rows) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


@dataclass
class LangPack:
    code: str
    path: Path
    meta: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.meta.get("name", self.code)

    @property
    def english_name(self) -> str:
        return self.meta.get("english_name", self.code)

    @property
    def mod_name(self) -> str:
        return self.meta["mod_name"]

    @property
    def needs_font_patch(self) -> bool:
        """Does this language need letters the game's font lacks (accents, ¿ ¡)? Then the atlas, the character string and the metrics are patched."""
        return bool(self.meta.get("font", {}).get("accents"))

    def platform(self, name: str) -> dict:
        """Layout parameters for one platform (``switch``, ``android``), with an empty dict as the default."""
        return dict(self.meta.get("platforms", {}).get(name, {}))

    def supports(self, platform: str) -> bool:
        return platform in self.meta.get("platforms", {})

    def text(self) -> dict[str, list[str]]:
        """``{fingerprint: segments}`` of the script. A pack without a script (English, for Android) gives ``{}``."""
        f = self.path / "text.jsonl"
        if not f.exists():
            return {}
        return {o["k"]: o["t"] for o in read_jsonl(f)}


def load_pack(path) -> LangPack:
    path = Path(path)
    meta_file = path / "lang.json"
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PackError(f"{meta_file}: cannot read the language file ({e})") from None
    for key in ("code", "name", "mod_name"):
        if key not in meta:
            raise PackError(f"{meta_file}: missing mandatory field {key!r}")
    if not CODE.match(meta["code"]):
        raise PackError(f"{meta_file}: {meta['code']!r} is not a language code (examples: es, en, pt-br)")
    if re.search(r"[\\/]", meta["mod_name"]) or meta["mod_name"] in ("", ".", ".."):
        raise PackError(f"{meta_file}: mod_name must be a single folder name")
    return LangPack(code=meta["code"], path=path, meta=meta)


def discover(langs_dir) -> list[LangPack]:
    """Every folder under ``langs_dir`` that has a readable ``lang.json``, sorted by code."""
    langs_dir = Path(langs_dir)
    found = []
    for d in sorted(langs_dir.iterdir()) if langs_dir.is_dir() else []:
        if (d / "lang.json").is_file():
            found.append(load_pack(d))
    return sorted(found, key=lambda p: p.code)


def get_pack(langs_dir, code: str) -> LangPack:
    for p in discover(langs_dir):
        if p.code == code:
            return p
    known = ", ".join(p.code for p in discover(langs_dir)) or "none"
    raise PackError(f"no language pack {code!r} under {langs_dir} (available: {known})")


def source_text_problems(root) -> list[str]:
    """Scan every JSON/JSONL/Markdown file under ``root`` for characters that look like the game's own script (SPEC-005/R-4)."""
    problems = []
    for f in sorted(Path(root).rglob("*")):
        if not f.is_file() or f.suffix not in (".json", ".jsonl", ".md", ".txt"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        bad = sorted({c for c in SOURCE_RANGES.findall(text) if c not in ALLOWED_SOURCE_CHARS})
        if bad:
            problems.append(f"{f}: {''.join(bad[:12])!r}")
    return problems
