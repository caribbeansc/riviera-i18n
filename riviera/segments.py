"""How a row of the script is cut into segments, and which blocks hold what.

A string of the script is a list of *segments*. Every ASCII comma and every
``V(id)`` (a voice clip) opens one; the comma is the separator, the commas that
belong to the text itself are full-width. ``;`` is a line break (``\\n`` inside
``cN`` colour segments). The engine converts ASCII to full-width when it draws, so
a translation is written in plain ASCII (see :func:`riviera.ips.encode`).
"""

from __future__ import annotations

import re

PREFIX = re.compile(r"^(V\([^)]*\)|c\d+)")

# The 41 blocks of the table (see riviera.nso). What each one holds:
STORY = list(range(11, 22)) + [32, 35, 40]      # dialogue, narration and system voices
DESC = list(range(22, 31)) + [31]               # place descriptions (22-30) and battle tips (31)
CHOICES = [10]                                  # the options the player picks inside dialogue
ITEMS = [36]                                    # items: the descriptions, not the names
UI = list(range(0, 10)) + [34, 37, 38, 39]      # exploration labels, menus, messages, banners
NAMES = [33, 36]                                # names of enemies, weapons, items, skills


def disp(s: str) -> str:
    """Readable text: no line breaks, and full-width turned into ASCII."""
    s = s.replace("\n", " ")
    s = re.sub(r";　*", " ", s)
    out = []
    for ch in s:
        o = ord(ch)
        if ch == "　":
            out.append(" ")
        elif ch == "＿":
            out.append("…")
        elif 0xFF01 <= o <= 0xFF5E:
            out.append(chr(o - 0xFEE0))
        elif ch == "’":
            out.append("'")
        elif ch == "−":
            out.append("-")
        else:
            out.append(ch)
    return re.sub(r" +", " ", "".join(out)).strip()


def split_segments(raw: str) -> list[tuple[str, str, str]]:
    """``[(separator, prefix, text)]`` for a raw string.

    Each ``V(id)`` opens a segment and so does every ASCII comma; the separator is
    the comma, or the group of ``;`` before a ``V(``, or ``''`` for the first one.
    The prefix is ``V(id)``, ``cN`` or ``''``. ``"".join(sep + prefix + text)`` gives
    the string back.
    """
    pieces = re.split(r"(,|;+(?=V\()|(?<![;,])(?=V\())", raw)
    if len(pieces) > 1 and pieces[0] == "" and pieces[1] == "":
        pieces = pieces[2:]                  # artificial cut: the string starts with V(
    seq = [("", pieces[0])] + [(pieces[k], pieces[k + 1]) for k in range(1, len(pieces) - 1, 2)]
    out = []
    for sep, seg in seq:
        m = PREFIX.match(seg)
        out.append((sep, m.group(1) if m else "", seg[m.end():] if m else seg))
    return out


def wanted(block: int, en: str) -> bool:
    """Is this row narrative text (dialogue, narration, descriptions, choices) that gets translated?"""
    if block in STORY or block in DESC or block in CHOICES:
        return True
    if block in ITEMS:      # descriptions have line breaks or are long; the names do not
        return ";" in en or len(disp(en)) > 28
    return False


def wanted_ui(block: int, en: str) -> bool:
    """Interface text with at least one Latin letter (symbols, digits and ``0p1.`` style formats are skipped)."""
    if block not in UI:
        return False
    core = re.sub(r"(?<![A-Za-z])p\d+|%\w|\{[^}]*\}", "", disp(en))
    return bool(re.search(r"[A-Za-z]", core))


def name_cat(block: int, row: int) -> str:
    """Kind of name by row (block 33 goes in stretches: enemies, weapons, items, skills, enemy types)."""
    if block == 36:
        return "event item"
    if row <= 149:
        return "enemy"
    if row <= 160:
        return "protagonists' weapon"
    if row <= 244:
        return "weapon"
    if row <= 306:
        return "item"
    if row <= 2158:
        return "skill"
    return "enemy type"


def wanted_name(block: int, en: str) -> bool:
    """Names (all of block 33, and the names, not the descriptions, of 36) with a Latin letter."""
    if block not in NAMES or (block == 36 and wanted(block, en)):
        return False
    core = re.sub(r"(?<![A-Za-z])p\d+|%\w|\{[^}]*\}", "", disp(en))
    return bool(re.search(r"[A-Za-z]", core))
