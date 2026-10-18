"""Rules a translated string must follow (SPEC-008). Pure functions: no files, no game.

A translation is a list of segments with exactly the segments of the original, the same markers and none of the
characters the engine cannot take. Errors break the game or the line composer; warnings are judgement calls.
"""

from __future__ import annotations

import re

from .packs import SOURCE_RANGES

#: Things the engine reads and the translator must leave alone: ``p1`` (a number slot), ``%d`` and the like, ``{}`` slots,
#: ``[Nightmare]`` names of options, ``B1`` (a button icon), ``R(12)``, and a handful of symbols the font draws.
TOKENS = re.compile(r"\bp\d+\b|%[a-zA-Z0-9]|\{[^}]*\}|\[[A-Za-z][A-Za-z ]*\]|\b[A-Za-z]\d\b|R\(\d+\)|[$^♪★∩∪⊂⊃↑↓←→￥・♥]")
SILENT = re.compile(r"^[….!?\s]*$")


def tokens(s: str) -> list[str]:
    return sorted(TOKENS.findall(s))


def check_entry(key: str, en: list[str], t, extra_forbidden: list[tuple[re.Pattern, str]] = ()) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` for one translation ``t`` of the displayed English segments ``en``."""
    errors, warns = [], []
    if not isinstance(t, list) or len(t) != len(en):
        return [f"{key}: {len(t) if isinstance(t, list) else '?'} segments, expected {len(en)}"], warns
    for i, (e_seg, s_seg) in enumerate(zip(en, t)):
        tag = f"{key}[{i}]"
        if not isinstance(s_seg, str):
            errors.append(f"{tag}: not text")
            continue
        if e_seg.strip() and not s_seg.strip():
            errors.append(f"{tag}: empty")
            continue
        stray = "".join(c for c in s_seg if c != "￥" and c not in e_seg and SOURCE_RANGES.match(c))
        if stray:
            errors.append(f"{tag}: Japanese, Korean, Chinese or full-width characters: {stray!r}")
        if re.search(r"[;|\n\t]", s_seg):
            errors.append(f"{tag}: contains ; | a tab or a line break (the composer breaks lines): {s_seg!r}")
        if SILENT.match(e_seg) and s_seg != e_seg:
            errors.append(f"{tag}: a silence, copy it as it is: {e_seg!r}")
        if tokens(e_seg) != tokens(s_seg):
            errors.append(f"{tag}: markers {tokens(e_seg)} -> {tokens(s_seg)}")
        for pattern, message in extra_forbidden:
            if pattern.search(s_seg):
                errors.append(f"{tag}: {message}")
        if s_seg != s_seg.strip() or "  " in s_seg:
            warns.append(f"{tag}: extra spaces")
        if len(s_seg) > 1.45 * len(e_seg) + 10:
            warns.append(f"{tag}: long ({len(s_seg)} vs {len(e_seg)}): {s_seg!r}")
        if re.search(r"\?\s*$", s_seg) and "¿" not in s_seg and len(s_seg) > 12:
            warns.append(f"{tag}: no ¿: {s_seg!r}")
        if re.search(r"!\s*$", s_seg) and "¡" not in s_seg and len(s_seg) > 14:
            warns.append(f"{tag}: no ¡: {s_seg!r}")
    return errors, warns


def unusual_chars(t: list[str], allowed: str) -> str:
    """Characters of a translation that are neither ASCII nor in ``allowed`` (the pack's ``validation.extra_chars``)."""
    seen = {c for seg in t for c in seg if ord(c) > 126 and c not in allowed}
    return "".join(sorted(seen))
