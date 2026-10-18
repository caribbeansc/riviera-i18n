"""The line composer: Spanish text -> the strings the game draws, broken at the real glyph widths.

Every kind of text has its own box, and a cap per block does not work: one wide row used
to inflate a whole block (block 26 to 1833 units, 23 to 1108, 37 to 2358, when nearly all of
their rows fit in ~800-900), and the Spanish came out wider than the real box. So the boxes are
deduced *from the English*, per kind of row, and the Spanish is made to fit them.

* Dialogue (blocks 11-21, 35) and the lines that have a voice clip are composed segment by
  segment, with the full-width band of the dialogue box. English never goes past 2 lines per
  page (9589 pages of one line and 8469 of two) and the Spanish must not either.
* Everything else is composed as a whole row (:func:`compose_row`): the segments of a row are
  *chained* the way the English chains them (:func:`seg_chains`), the text is wrapped into the
  fewest lines that fit the box and balanced, and bullet lists get one bullet per line.

Units are the engine's: one full-width cell is 68, ~0.65 px on a 1280 px screen.
"""

from __future__ import annotations

import collections
import re

from . import ips, segments
from .packs import fingerprint

HEADER = ips.HEADER

# Blocks whose box takes the whole width of the screen (dialogue and voices): they may go past the usual English width
# (tested in the game: lines of up to ~1500 units show whole). The rest (descriptions, items, battle tips) have fixed-size
# boxes and are fitted strictly to the width and the number of lines of the English.
SOFT_BLOCKS = set(range(11, 22)) | {35}
UI_BLOCKS = set(segments.UI)                       # labels, menus and messages: one line if the English is one line
DESC_BLOCKS = set(range(22, 31))                   # place descriptions (and their event messages): the "Stage Start" box is a single one
TOL = 1.15                                         # slack over the widest English line of the row itself (interface boxes)
UI_TIGHT = 1.25                                    # interface text with several English lines: tight box = widest English line x this
UI_KS = (1.0, 1.15, 1.3, 1.5)                      # and, if the Spanish does not fit in the English lines, widened by these factors


def seg_chains(segs):
    """Group the segments of a row into *chains*.

    A segment FOLLOWS the previous one (the text is drawn on, and the comma separates them: the comma IS drawn, it is the
    English text's own comma, "[Nightmare], which is...") if its English starts with a space (", \\nhas been added...": that is
    how the interface rows were typed); otherwise it is a page of its own (the inscriptions on the tombs are three pages of several
    lines each). A segment with a tag (``cN``) opens a chain.
    Tested in the game (probe on the difficulty screen): in static text the separating comma shows as a normal comma, the text of
    the next segment goes on the same line and a ``\\n`` at the start of that segment breaks the line.
    """
    out = []
    for i, (sep, prefix, orig) in enumerate(segs):
        if i > 0 and orig.startswith(" ") and not prefix:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def row_shape(en_raw, M):
    """``(lines, width of the widest in engine units, texts of the lines)`` of the English of a row. Lines are counted per chain of
    segments (:func:`seg_chains`): ``lines`` is the maximum over the chains and the width that of the widest line of all;
    only lines with text count."""
    segs = segments.split_segments(en_raw)
    best, allw, alll = 1, [], []
    for ch in seg_chains(segs):
        full = "".join(segs[k][2] for k in ch)
        lines = [segments.disp(x) for x in re.split(r";|\n", full)]
        lines = [x for x in lines if x.strip()]
        best = max(best, len(lines)); alll += lines; allw += [M.line(x) for x in lines]
    return best, (max(allw) if allw else 0), alll


def is_bullets(lines):
    """Is the English a list with one "・" bullet per line? (difficulty and mode descriptions)"""
    return sum(1 for x in lines if x.lstrip().startswith("・")) >= 2


def has_voice(en_raw):
    return any(p.startswith("V(") for _, p, _ in segments.split_segments(en_raw))


def row_level(r):
    """Is the row composed whole as one text (chained segments) instead of segment by segment? Yes for everything that is
    neither dialogue nor a line with a voice clip (each voice clip is a page with its own split into lines)."""
    return r["block"] not in SOFT_BLOCKS and r["block"] != 33 and not has_voice(r["en"])


def percentile(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(len(v) * p))]


def group_of(block, row, en):
    """Sub-group with a box of its own inside a block: the stretches of 33 (enemies, weapons, items, skills) and names
    against descriptions in 36. The other blocks are a single group."""
    if block == 33:
        return segments.name_cat(33, row)
    if block == 36:
        return "description" if segments.wanted(36, en) else "name"
    return ""


class Caps(dict):
    """Result of :func:`block_caps`: the plain ``{(block, group): (lines, width)}`` dict plus ``groups``, the per-row boxes (see box_groups)."""
    groups = None


def box_groups(rows, M):
    """Box widths deduced from the English, per kind of row (only rows without a voice outside the dialogue, which are the ones
    composed whole): ``bmax[block]`` widest line; ``bul_cap``/``bul_lines[block]`` the common box of the bullet lists;
    ``desc5``/``desc`` the box of the place descriptions (rows of 5 lines / of 4 or more); ``gmax``/``gcnt[(block, lines)]``
    rows of other lengths in the place blocks (event messages)."""
    g = {"bmax": collections.defaultdict(int), "bul_cap": collections.defaultdict(int), "bul_lines": collections.defaultdict(int),
         "ui_w": collections.defaultdict(list),
         "desc5": 0, "desc": 0, "gmax": collections.defaultdict(int), "gcnt": collections.defaultdict(int)}
    for r in rows:
        if not row_level(r):
            continue
        b = r["block"]
        n, W, lines = row_shape(r["en"], M)
        g["bmax"][b] = max(g["bmax"][b], W)
        if b in UI_BLOCKS and n >= 2 and not is_bullets(lines):
            g["ui_w"][(b, n)].append(W)
        if is_bullets(lines):
            g["bul_cap"][b] = max(g["bul_cap"][b], W); g["bul_lines"][b] = max(g["bul_lines"][b], n)
        elif b in DESC_BLOCKS:
            if n >= 4:
                g["desc"] = max(g["desc"], W)
                if n >= 5:
                    g["desc5"] = max(g["desc5"], W)
            else:
                g["gmax"][(b, n)] = max(g["gmax"][(b, n)], W); g["gcnt"][(b, n)] += 1
    return g


def block_caps(rows, M):
    """Per block (and group), from the English: ``(maximum lines per segment, maximum line width in engine units)``."""
    widths, nlines = collections.defaultdict(list), collections.defaultdict(int)
    for r in rows:
        k = (r["block"], group_of(r["block"], r["row"], r["en"]))
        for _, _, text in segments.split_segments(r["en"]):
            lines = re.split(r";|\n", text)
            nlines[k] = max(nlines[k], len(lines))
            for ln in lines:
                d = segments.disp(ln)
                if d:
                    widths[k].append(M.line(d))
    caps = Caps()
    for k, w in widths.items():
        caps[k] = (max(2, nlines[k]) if k[0] in segments.STORY else nlines[k],
                   percentile(w, 0.99) if len(w) >= 200 else max(w))
    caps.groups = box_groups(rows, M)
    return caps


def row_layout(r, caps, M):
    """``(maximum lines, maximum width, bullets?)`` of a row that is composed whole (:func:`row_level`). The width comes from the
    box the English uses:

    * bullet lists: the common box of all the lists of the block (each bullet on its line);
    * interface (blocks 0-9, 34, 37-39) with several lines: the cap is the larger of the widest English line of the row x TOL
      and the typical box of its family (p90 of the rows of the same block and number of lines, if there are 8 or more);
      :func:`compose_row` then tightens it to the English lines with :func:`ui_cap` (widest English line x UI_TIGHT) and only
      uses this cap if the Spanish does not fit that way. With a single line: the cap of the block, and 1.5x if the English is short;
    * place descriptions (22-30): one common box (that of the 5-line rows); the event messages, the box of their block and number
      of lines if there are enough rows, or their own line x TOL;
    * every other block: the cap of the block.
    """
    b = r["block"]; g = group_of(b, r["row"], r["en"])
    base_lines, base_cap = caps[(b, g)]
    n, W, lines = row_shape(r["en"], M)
    G = caps.groups
    if is_bullets(lines):
        return G["bul_lines"][b], max(G["bul_cap"][b], W), True
    if b in UI_BLOCKS:
        if n == 1:
            cap = base_cap
            if W <= 600:
                cap = min(cap, max(int(W * 1.5), W + 200))
            return 1, cap, False
        fam = G["ui_w"][(b, n)]            # the family (same block and number of lines) shares screens and boxes: its p90 is the typical box
        box = percentile(fam, 0.9) if len(fam) >= 8 else 0
        return n, max(W, box, min(int(W * TOL), G["bmax"][b])), False
    if b in DESC_BLOCKS:
        if n >= 4:
            return base_lines, max(G["desc5"], W), False
        k = (b, n)
        cap = G["gmax"][k] if G["gcnt"][k] >= 4 else int(W * TOL)
        return max(n, 2), max(cap, W), False
    return base_lines, base_cap, False


def seg_limits(r, orig, caps, M):
    """``(maximum lines, maximum width)`` of a segment ``orig`` (raw English) of row ``r``. In labels and messages the Spanish has
    the same lines as the English, and if the English is a word or a short sentence the width does not go past 1.5 times
    its own (or +200 units): they tend to sit in buttons and tight columns."""
    if row_level(r) and getattr(caps, "groups", None) is not None and (r["block"] in UI_BLOCKS or r["block"] in DESC_BLOCKS):
        max_lines, cap, _ = row_layout(r, caps, M)
        return max_lines, cap
    g = group_of(r["block"], r["row"], r["en"])
    max_lines, cap = caps[(r["block"], g)]
    if r["block"] in UI_BLOCKS or g in ("name",) or r["block"] == 33:
        n_en = len(re.split(r";|\n", orig))
        max_lines = n_en
        if n_en == 1 and r["block"] in UI_BLOCKS:
            en_w = M.line(segments.disp(orig))
            if en_w <= 600:
                cap = min(cap, max(int(en_w * 1.5), en_w + 200))
    return max_lines, cap


def wrap_words(words, cap, M):
    """Split the list of words into the fewest lines of width <= cap and balance them (all as even as possible).
    Returns lists of word indices, one per line."""
    ww = [M.line(ips.encode(w, "ascii", False)) for w in words]
    sp = M.glyph(" ")

    def greedy(c):
        lines, cur, w = [], [], 0
        for k, wl in enumerate(ww):
            if cur and w + sp + wl > c:
                lines.append(cur); cur, w = [k], wl
            else:
                cur.append(k); w = w + sp + wl if len(cur) > 1 else wl
        lines.append(cur)
        return lines

    first = greedy(cap)
    n = len(first)
    if n == 1:
        return first
    lo, hi = max(ww), cap                          # balancing: the smallest cap that still gives n lines
    while hi - lo > 4:
        mid = (lo + hi) // 2
        if len(greedy(mid)) <= n:
            hi = mid
        else:
            lo = mid
    return greedy(hi) if len(greedy(hi)) == n else first


def wrap_units(text, cap, M):
    """Split ``text`` into the fewest lines of width <= cap and balance them."""
    words = text.split(" ")
    return [" ".join(words[k] for k in ln) for ln in wrap_words(words, cap, M)]


def chain_shape(segs, ch, M):
    """``(lines with text, width of the widest)`` of the English of a chain of segments."""
    lines = [segments.disp(x) for x in re.split(r";|\n", "".join(segs[k][2] for k in ch))]
    lines = [x for x in lines if x.strip()]
    return len(lines), max((M.line(x) for x in lines), default=0)


def ui_cap(words, n_en, w_en, cap, M):
    """Box of an interface chain whose English has ``n_en`` >= 2 lines (menu help, confirmation boxes...): it was designed for
    those lines, so the Spanish is split into the same ones, at the width of the widest English line x UI_TIGHT (x UI_KS if it does
    not fit). With the typical box of the family (``cap``, p90 of the block: 1904 u in block 37) some rows came out on a single long
    line (the 1597 u "overwrite" box; the menu help glued to the "Difficulty" box). If it does not fit in the English lines
    even so, ``cap`` applies."""
    for k in UI_KS:
        c = int(UI_TIGHT * k * w_en)
        if c >= cap:
            break
        if len(wrap_words(words, c, M)) <= n_en:
            return c
    return cap


def compose_row(r, es, caps, M):
    """Final text of a row that is composed whole (:func:`row_level`). Each chain of segments is composed as a single text: the Spanish
    segments are chained like the English ones (the separating comma is drawn, so the segment does not repeat it) and the text is split
    into lines at the width of the box of the row (:func:`row_layout`; in the interface with several English lines, the tight one of
    :func:`ui_cap`); in bullet lists, one bullet per line. A break that falls exactly between two segments of a chain goes at the start
    of the second (like the English: ", \\nhas been..."); inside a line the second segment carries a space. Pages (separate chains) are
    composed each on its own. Returns ``(string, lines of the longest chain, maximum lines, cap, real width of the widest line, encoded
    words)``."""
    segs = segments.split_segments(r["en"])
    max_lines, cap, bullets = row_layout(r, caps, M)
    ui_multi = r["block"] in UI_BLOCKS and not bullets
    chains = seg_chains(segs)
    chain_of = {k: ci for ci, ch in enumerate(chains) for k in ch}
    # the separating comma IS drawn in static text (tested in the game: "dddd," and "hhhh, iiii"), so a segment that is not the
    # last of its chain cannot end in a comma (it would show ",,")
    es = [t.rstrip(" ,，") if i + 1 < len(es) and chain_of.get(i + 1) == chain_of[i] else t for i, t in enumerate(es)]
    toks = [(w, i) for i, text in enumerate(es) for w in text.split(" ") if w]
    words = [w for w, _ in toks]
    enc = [ips.encode(w, "ascii", False) for w in words]
    line_of, n_max, widest = {}, 0, 0
    for ci, ch in enumerate(chains):
        idx = [ti for ti, (_, sg) in enumerate(toks) if chain_of[sg] == ci]
        groups, cur = [], []
        for ti in idx:
            if bullets and words[ti].startswith("・") and cur:
                groups.append(cur); cur = []
            cur.append(ti)
        if cur:
            groups.append(cur)
        n = 0
        n_en, w_en = chain_shape(segs, ch, M) if ui_multi else (0, 0)
        for grp in groups:
            gcap = ui_cap([words[t] for t in grp], n_en, w_en, cap, M) if n_en >= 2 else cap
            for ln in wrap_words([words[t] for t in grp], gcap, M):
                for k in ln:
                    line_of[grp[k]] = (ci, n)
                widest = max(widest, M.line(" ".join(enc[grp[k]] for k in ln)))
                n += 1
        n_max = max(n_max, n)
    out, prev, ti = [], None, 0
    for i, (sep, prefix, orig) in enumerate(segs):
        out.append(sep + prefix)
        if i == chains[chain_of[i]][0]:
            prev = None                                        # a page starts: its first word takes no separator
        joiner = "\n" if "\n" in orig else ";"
        while ti < len(toks) and toks[ti][1] == i:
            li = line_of[ti]
            if prev is not None:
                out.append(joiner if li != prev else " ")
            out.append(enc[ti]); prev = li; ti += 1
    return "".join(out), n_max, max_lines, cap, widest, enc


def free_regions(nso, rows, slots_idx=(1, 2, 3)):
    """Free memory: the Japanese, Korean and Chinese strings of the rows (unused while the game runs in English) that nobody
    else references or overlaps, neither through another pointer nor through a direct access of the code.
    Returns ``(start, end)`` memory intervals."""
    import bisect

    refs = collections.Counter(nso.relocs.values())
    targets = sorted(refs)
    out, seen = [], set()
    for r in rows:
        for q in slots_idx:
            a = nso.relocs[r["slots"][q]]
            if a in seen or refs[a] != 1:
                continue
            seen.add(a)
            ln = len(nso.cstr(a))
            if ips.code_uses(nso, a, ln):
                continue                                           # the code uses it directly (e.g. "/")
            i = bisect.bisect_right(targets, a)
            if i < len(targets) and targets[i] <= a + ln:
                continue                                           # another pointer points inside
            j = i - 2
            if j >= 0 and nso.textish(targets[j]) and targets[j] + len(nso.cstr(targets[j])) >= a:
                continue
            out.append((a, a + ln + 1))
    return out


def build_text(nso, rows, db, M, charset, soft):
    """Compose every translated row. Returns ``(want, overflow, skipped, chars, caps)``: ``want`` maps the slot of the English
    pointer to ``(original address, new bytes)``; ``overflow`` lists the rows that do not fit their box; ``skipped`` counts rows
    whose segments do not match the translation; ``chars`` counts the characters used."""
    caps = block_caps(rows, M)
    want, overflow, skipped, chars = {}, [], 0, collections.Counter()
    for r in rows:
        es = db.get(fingerprint(r["en"]))
        if es is None:
            continue
        segs = segments.split_segments(r["en"])
        if len(segs) != len(es):
            skipped += 1
            continue
        if row_level(r):                                  # rows without voice outside the dialogue: the whole text, chained
            raw, nl, mx, cap, widest, enc = compose_row(r, es, caps, M)
            for w in enc:
                chars.update(w)
            if nl > mx or widest > cap:
                overflow.append({"block": r["block"], "row": r["row"], "lines": nl, "max": mx, "width": widest, "cap": cap,
                                 "text": " ".join(es)[:70]})
            slot = r["slots"][0]
            want[slot] = (nso.relocs[slot], raw.encode("utf-8"))
            continue
        parts = []
        for (sep, prefix, orig), text in zip(segs, es):
            max_lines, cap = seg_limits(r, orig, caps, M)
            lines = wrap_units(text, cap, M)
            if len(lines) > max_lines and soft > 1 and r["block"] in SOFT_BLOCKS:   # only in dialogue (full-width box)
                alt = wrap_units(text, int(cap * soft), M)
                if len(alt) <= max_lines:
                    lines = alt
            if len(lines) > max_lines:
                overflow.append({"block": r["block"], "row": r["row"], "lines": len(lines), "max": max_lines, "text": text[:70]})
            joiner = "\n" if "\n" in orig else ";"
            enc = [ips.encode(ln, "ascii", False) for ln in lines]
            for ln in enc:
                chars.update(ln)
            lead = re.match(r" *", orig).group()          # the English has a space at the start of the segment after the separating comma: kept (without it the words stick together)
            parts.append(sep + prefix + lead + joiner.join(enc))
        raw = "".join(parts)
        slot = r["slots"][0]
        want[slot] = (nso.relocs[slot], raw.encode("utf-8"))
    return want, overflow, skipped, chars, caps
