"""The artwork of the Android build: the Switch pictures of the user's dump, adapted to what only the Android app draws.

The Android app is the Switch game with a touch interface, so most of its pictures exist in the Switch containers too. Building the
Android artwork is therefore mostly **reading the user's Switch dump** and fitting what it finds into the Android containers:

1. *Whole files.* Every file of the Switch ``data_en.bin`` (English pictures; for a translated language, the translated packages of
   :func:`riviera.images.translated_packages`) replaces the Android file of the same path, except the ones Android draws differently
   (:data:`EXCLUSIVE_PACKS`, :data:`EXCLUSIVE_FILES`).
2. *Packages only Android has* (the options, the save screens, the touch interface...): the Android package is kept and **each picture is
   replaced by name** with the Switch one: the same size is taken as is, another size is taken at its own size too (the engine draws every
   picture at its native size) unless the Android picture is a big one that may be a sprite sheet. Pictures with a different size and the ones
   that exist only in Android are adjusted by :func:`derive` (scaled to the height of the Android picture, copied, or fitted) following
   :data:`RULES`.
3. *What the dump cannot give*: the labels the Android app draws that Switch does not have ("Wide screen", the cloud-backup screen, the
   voice-language buttons, ...). They come with the language pack, ``langs/<code>/android/images/manifest.json``, in the formats of
   :mod:`riviera.images` plus ``layer`` (below). Nothing of the game is stored there: ``full`` pictures are text on an empty canvas,
   ``delta`` ones the changed pixels over the user's original, and ``layer`` ones a text layer composed with pieces **copied from the user's
   own picture at build time**.
4. *Code-made pictures*: the LOOK sprites (:mod:`riviera.android.sprites`, from the letters of the Switch picture) and the labels of the
   button-press minigames (the Switch labels fitted into the canvas of the Android files).

``layer`` entries of the manifest (``{"kind": "layer", "size": [w, h], "ops": [...], "bleed": [r, g, b], "encode": "exact" | "plain"}``): an empty
transparent canvas of ``size`` receives the ops in order:

* ``{"op": "layer", "file": "x.png", "at": [x, y]}``: a picture of the pack (our text), composed over the canvas;
* ``{"op": "copy", "from": "<entry>" | null, "box": [l, t, r, b], "to": [x, y]}``: a piece of the user's own original of that entry (``null`` =
  the entry itself), composed over the canvas;
* ``{"op": "erase_enclosed"}``: paints with the flat colour of the button everything printed on it (:func:`erase_enclosed`), found from the
  pixels the canvas holds at that point. It is how the Japanese label of a button disappears without the pack storing anything of it.

``bleed`` gives the RGB of the transparent pixels. ``encode``: ``exact`` (the default) saves a lossless WebP that keeps the colour of the transparent
pixels; ``plain`` the way the other pictures are saved.
"""

from __future__ import annotations

import fnmatch
import io
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .. import font, pck, sge
from .. import images as swimages
from ..packs import LangPack
from . import sprites
from .assets import AndroidAssets
from . import AndroidError

#: Packages the Android app builds differently from Switch's: kept, and their pictures replaced by name (or by the pack's own).
EXCLUSIVE_PACKS = ("data/System/config.pck", "data/System/systemTexture.pck", "data/event/extra.pck", "data/event/r_title.pck", "data/Save/Save.pck")
#: Files that exist in both builds with different content: left as the Android ones (the credits stay as they are).
EXCLUSIVE_FILES = ("data/System/staffrole02.webp", "data/extra/ex3bg02.webp")
#: The package with the font atlas and the touch buttons: rebuilt on its own, never by name.
ATLAS_PACK = "data/System/systemTexture3.pck"
#: Files of the inventory: the exclusive packages, the packages and loose pictures only Android has.
INVENTORY_FILES = (*EXCLUSIVE_PACKS, "data/System/loading.pck", "data/Backup/backup.pck", "data/event/bg250.pck", "data/System/staffrole02.webp",
                   "data/extra/ex3bg02.webp", "data/System/background.webp", "data/skillname/eskillName00.webp")
AT_FILES = ["data/at/at_text%d.webp" % i for i in range(6)] + ["data/at/at_caption.webp"]
#: Where the Switch has the pictures that Android keeps as loose files.
SWITCH_ALIAS = {f: ("data/System/systemTexture.pck", f.rsplit("/", 1)[1]) for f in AT_FILES}
SWITCH_ALIAS["data/event/r_title.pck::ext1_jn00.webp"] = ("data/event/r_title.pck", "ext1_en00.webp")


class AndroidImageError(AndroidError):
    """A picture of the Android build cannot be made."""


# What to do with each picture of the inventory that differs from Switch's or that Switch lacks ("file::entry", fnmatch patterns, first match
# wins): OMIT = already in English (or art without text); GENERATE = the pack draws it; COPY = the Switch picture at its natural size;
# FIT = scaled to the exact size of the Android one; anything else: scaled to the height of the Android picture ("height").
OMIT = [
    "data/System/config.pck::soundset3_on.webp", "data/System/config.pck::soundset5_on.webp",
    "data/System/systemTexture.pck::skl_win_base.webp", "data/System/systemTexture.pck::skl_win_head.webp",
    "data/System/systemTexture.pck::trigger_mode.webp", "data/System/systemTexture.pck::teamedit.webp",
    "data/System/systemTexture.pck::itemselect.webp", "data/System/systemTexture.pck::imp_atk.webp",
    "data/System/systemTexture.pck::imp_mag.webp", "data/System/systemTexture.pck::checklist_o*.webp",
    "data/System/systemTexture.pck::rage.webp", "data/System/systemTexture.pck::btlparts.webp",
    "data/System/systemTexture.pck::enemy_skill_type.webp", "data/System/systemTexture.pck::skl_win_attrname.webp",
    "data/System/systemTexture.pck::odg.webp", "data/System/systemTexture.pck::totaldmg*.webp",
    "data/System/systemTexture.pck::atkhits.webp", "data/System/systemTexture.pck::attackhitsnum.webp",
    "data/System/systemTexture.pck::tap_to_quest.webp",
    "data/event/r_title.pck::title_*_s.webp", "data/event/r_title.pck::intellectual_txt.webp",
    "data/Save/Save.pck::save_nodata.webp", "data/System/loading.pck::*", "data/event/bg250.pck::*",
    "data/System/background.webp::*", "data/System/staffrole02.webp::*",
    "data/event/extra.pck::soundset3_on.webp", "data/event/extra.pck::soundset5_on.webp", "data/event/extra.pck::mininame?.webp",
    "data/Backup/backup.pck::backup_backup_button_zabuton.webp", "data/Backup/backup.pck::backup_data_waku.webp",
    "data/Backup/backup.pck::backup_mb.webp", "data/Backup/backup.pck::buckup_num_mb.webp",
]
GENERATE = [
    "data/System/config.pck::txt_view_width.webp", "data/System/config.pck::txt_view_width2.webp",
    "data/System/systemTexture.pck::important.webp", "data/skillname/eskillName00.webp::*", "data/Backup/backup.pck::*",
]
COPY = [
    "data/System/systemTexture.pck::largename?.webp", "data/System/systemTexture.pck::evshot*.webp",
    "data/System/systemTexture.pck::at_text?.webp", "data/System/systemTexture.pck::at_caption.webp",
    "data/System/systemTexture.pck::telop_battle_infomation.webp", "data/System/systemTexture.pck::telop25_difficult_level.webp",
    "data/at/*::*", "data/event/r_title.pck::ext1_en00.webp", "data/event/r_title.pck::ext1_jn00.webp",
]
FIT = ["data/System/config.pck::dot_filter_chara_on.webp"]

#: Width limits of the options screen: its labels sit in two fixed columns (430 and 892 units wide).
CONFIG_LABEL_CAP, CONFIG_TEXT_CAP = 430, 892
#: Pictures at least this big in Android may be sprite sheets with coordinates fixed in the code: they are not replaced by another size.
SHEET_MIN = (256, 160)


# ---------------------------------------------------------------- helpers --

def base_name(entry: str) -> str:
    return entry.replace("\\", "/").split("/")[-1].lower()


def entries_by_base(blob: bytes) -> dict[str, bytes]:
    return {base_name(pck.entry_name(e[0])): e[1] for e in pck.read_pck(blob)[1]}


def dims(blob: bytes):
    try:
        return Image.open(io.BytesIO(blob)).size
    except Exception:
        return None


def resize(im: Image.Image, size) -> Image.Image:
    """Scale without the colour of the transparent pixels staining the edges (premultiplied alpha)."""
    size = (max(1, int(size[0])), max(1, int(size[1])))
    if im.size == size:
        return im
    return im.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def matches(label: str, patterns) -> bool:
    return any(fnmatch.fnmatch(label, p) or fnmatch.fnmatch(label.lower(), p.lower()) for p in patterns)


def classify(label: str) -> str:
    if matches(label, OMIT):
        return "omit"
    if matches(label, GENERATE):
        return "generate"
    if matches(label, FIT):
        return "fit"
    if matches(label, COPY):
        return "copy"
    return "height"


def derive(action: str, switch_im: Image.Image, android_im: Image.Image, archive: str, name: str) -> Image.Image:
    """The Android picture made from the Switch one: ``copy`` = as it is (the engine draws it at its own size), ``fit`` = scaled to the
    exact size of the Android one, ``height`` = scaled to its height keeping the width (the same proportion of letter); the labels of the
    options screen are squeezed into their column."""
    if action == "copy":
        return switch_im
    if action == "fit":
        return resize(switch_im, android_im.size)
    k = android_im.size[1] / switch_im.size[1]
    im = resize(switch_im, (round(switch_im.size[0] * k), android_im.size[1]))
    cap = config_cap(archive, name)
    if cap and im.size[0] > cap:
        im = resize(im, (cap, im.size[1]))
    return im


def config_cap(archive: str, name: str):
    if not archive.endswith("config.pck") or not name.startswith("txt_"):
        return None
    if name.endswith("2.webp") or "_txt_" in name or name.endswith("_2.webp"):
        return CONFIG_TEXT_CAP
    return CONFIG_LABEL_CAP


# ------------------------------------------------------------------ donor --

class Donor:
    """The Switch side: its English pictures and, for a translated language, the translated packages built over them."""

    def __init__(self, romfs, translated: dict[str, bytes] | None = None):
        romfs = Path(romfs)
        self.translated = translated or {}
        self._archives = [sge.Archive(romfs / "data_en.bin"), sge.Archive(romfs / "data.bin")]
        self._where = [{p: (n, i, v) for p, n, i, v in a.walk()} for a in self._archives]

    def close(self) -> None:
        for a in self._archives:
            a.close()

    def english_paths(self) -> set[str]:
        return set(self._where[0])

    def english(self, path: str) -> bytes | None:
        hit = self._where[0].get(path)
        return self._archives[0].read(*hit) if hit else None

    def get(self, path: str) -> bytes | None:
        """The picture or package as the translated game has it: translated, else the English original, else the common one."""
        if path in self.translated:
            return self.translated[path]
        for arc, where in zip(self._archives, self._where):
            if path in where:
                return arc.read(*where[path])
        return None


# ----------------------------------------------------------- pack images --

def erase_enclosed(im: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """``(picture, box)``: ``im`` with the text printed on a flat-coloured button painted over with the colour of the button, and the box
    ``(left, top, right, bottom)`` (inclusive) that the text occupied.

    The body of the button is a flat colour (the most frequent opaque colour that is neither nearly white nor nearly black) and the text
    is surrounded by it: flooding from the corner through everything that is not body (the outline, the shadow, the transparency), what is
    not reached is the text, with its antialiasing; it is grown by two pixels and painted with the colour of the body. Only the pixels of
    the picture itself are used."""
    w, h = im.size
    a = im.convert("RGBA")
    px = a.load()
    counts = Counter(px[x, y][:3] for y in range(h) for x in range(w) if px[x, y][3] > 250 and 60 < sum(px[x, y][:3]) / 3 < 215)
    if not counts:
        raise AndroidImageError("the picture has no flat body to erase text from")
    body = counts.most_common(1)[0][0]

    def near(c):
        return sum(abs(c[i] - body[i]) for i in range(3)) <= 36

    m = Image.new("L", (w, h), 255)
    mp = m.load()
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 200 and near(px[x, y][:3]):
                mp[x, y] = 0
    ImageDraw.floodfill(m, (0, 0), 128, thresh=0)                       # the outside: all that is not body and reaches the corner
    text = [(x, y) for y in range(h) for x in range(w) if mp[x, y] == 255 and px[x, y][3] > 0]
    if not text:
        raise AndroidImageError("no text found on the button")
    xs, ys = [p[0] for p in text], [p[1] for p in text]
    erase = Image.new("L", (w, h), 0)
    ep = erase.load()
    for x, y in text:
        ep[x, y] = 255
    ep = erase.filter(ImageFilter.MaxFilter(5)).load()
    for y in range(h):
        for x in range(w):
            if ep[x, y] and mp[x, y] != 128 and px[x, y][3] > 200:
                px[x, y] = body + (255,)
    return a, (min(xs), min(ys), max(xs), max(ys))


def paste_over(canvas: Image.Image, im: Image.Image, at) -> None:
    """Compose ``im`` over ``canvas`` with its top left corner at ``at`` (it may fall partly outside)."""
    tmp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    tmp.paste(im, tuple(at))
    canvas.alpha_composite(tmp)


def compose_layers(spec: dict, pack_dir: Path, originals: dict[str, bytes], own: bytes) -> bytes:
    """A ``layer`` entry of the manifest (see the module docstring)."""
    w, h = spec["size"]
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for op in spec["ops"]:
        if op["op"] == "layer":
            paste_over(canvas, Image.open(pack_dir / "images" / op["file"]).convert("RGBA"), op["at"])
        elif op["op"] == "copy":
            src = own if op.get("from") is None else originals[op["from"]]
            paste_over(canvas, swimages.decode(src).crop(tuple(op["box"])), op["to"])
        elif op["op"] == "erase_enclosed":
            canvas = erase_enclosed(canvas)[0]
        else:
            raise AndroidImageError(f"unknown operation {op['op']!r} in a layer")
    if spec.get("bleed"):
        canvas = sprites.bleed(canvas, tuple(spec["bleed"]))
    if spec.get("encode", "exact") == "plain":
        return swimages.encode_webp(canvas)
    return sprites.encode_webp_exact(canvas)


def pack_images(pack: LangPack, assets: AndroidAssets) -> tuple[dict[str, dict[str, bytes]], list[str]]:
    """``({package path: {entry key: new bytes}}, warnings)`` for the pictures the language pack ships for Android. The key is the entry's
    base name (lowercase); a loose file is the package itself with the key ``*``."""
    pack_dir = pack.path / "android"
    manifest = swimages.load_manifest(pack_dir)
    out: dict[str, dict[str, bytes]] = {}
    warnings: list[str] = []
    for package, entries in swimages.packages(manifest, "android").items():
        original = assets.read(package)
        if original is None:
            raise AndroidImageError(f"the app has no {package}: is this the version of the app the pack was made for?")
        loose = not package.endswith(".pck")
        originals = {"*": original} if loose else entries_by_base(original)
        got = out.setdefault(package, {})
        for key, spec in entries.items():
            if key not in originals:
                raise AndroidImageError(f"{package} has no picture called {key}")
            own = originals[key]
            if spec.get("base") and swimages.sha1(own) != spec["base"]:
                warnings.append(f"{package}/{key}: not the picture this translation was made against")
            if spec["kind"] == "full":
                got[key] = (pack_dir / "images" / spec["file"]).read_bytes()
            elif spec["kind"] == "delta":
                overlay = Image.open(pack_dir / "images" / spec["overlay"])
                mask = Image.open(pack_dir / "images" / spec["mask"])
                got[key] = swimages.encode_webp(swimages.apply_delta(swimages.decode(own), overlay, mask))
            elif spec["kind"] == "layer":
                got[key] = compose_layers(spec, pack_dir, originals, own)
            else:
                raise AndroidImageError(f"{package}/{key}: unknown kind {spec['kind']!r}")
    return out, warnings


# -------------------------------------------------------------- inventory --

def inventory(assets: AndroidAssets, donor: Donor) -> list[tuple[str, str, str]]:
    """``[(file, entry or "-", comparison)]`` of the Android pictures that may need localizing, compared with Switch's of the same file:
    ``same`` (same bytes), ``same_size`` (same size, other content), ``other_size`` (another size) or ``no_counterpart`` (Switch has none)."""
    files = list(INVENTORY_FILES) + sorted(p for p in assets.paths() if p.startswith("data/at/"))
    rows = []
    for f in files:
        a = assets.read(f)
        if a is None:
            continue
        s = donor.get(f)
        if f.endswith(".pck"):
            sb = entries_by_base(s) if s else {}
            for name, blob in ((pck.entry_name(e[0]), e[1]) for e in pck.read_pck(a)[1]):
                sv = sb.get(base_name(name))
                kind = "no_counterpart" if sv is None else ("same" if sv == blob else ("same_size" if dims(blob) == dims(sv) else "other_size"))
                rows.append((f, name, kind))
        else:
            kind = "no_counterpart" if s is None else ("same" if s == a else ("same_size" if dims(a) == dims(s) else "other_size"))
            rows.append((f, "-", kind))
    return rows


def derived_images(assets: AndroidAssets, donor: Donor, say) -> tuple[dict[str, dict[str, bytes]], list[str], dict]:
    """The pictures made from Switch's by :func:`derive`: ``{package: {entry key: new bytes}}`` (loose files use the key ``*``)."""
    out: dict[str, dict[str, bytes]] = defaultdict(dict)
    warnings, counts = [], defaultdict(int)
    for f, entry, kind in inventory(assets, donor):
        if kind not in ("other_size", "no_counterpart"):
            continue
        name = base_name(entry) if entry != "-" else base_name(f)
        label = f"{f}::{name}" if entry != "-" else f"{f}::*"
        action = classify(label)
        counts[action] += 1
        if action in ("omit", "generate") or f in AT_FILES:          # the minigame labels are made by at_images()
            continue
        sa, se = SWITCH_ALIAS.get(f, SWITCH_ALIAS.get(f"{f}::{name}", (f, entry)))
        sblob = donor.get(sa)
        if sblob is None:
            warnings.append(f"{f}/{name}: Switch has no counterpart")
            continue
        if sa.endswith(".pck"):
            s_entry = entries_by_base(sblob).get(base_name(se))
            if s_entry is None:
                warnings.append(f"{f}/{name}: Switch has no counterpart")
                continue
        else:
            s_entry = sblob
        a_blob = assets.read(f)
        a_entry = entries_by_base(a_blob)[name] if f.endswith(".pck") else a_blob
        im = derive(action, swimages.decode(s_entry), swimages.decode(a_entry), f, name)
        out[f]["*" if entry == "-" else (name if name.endswith(".webp") else name.rsplit(".", 1)[0] + ".webp")] = swimages.encode_webp(im)
        if im.size[0] > swimages.decode(a_entry).size[0]:
            warnings.append(f"{f}/{name}: wider than the Android picture")
    say(f"  pictures to adjust: {dict(counts)}")
    return out, warnings, dict(counts)


def at_images(assets: AndroidAssets, donor: Donor) -> dict[str, bytes]:
    """The labels of the button-press minigames (loose files only Android has): the Switch labels of ``systemTexture.pck`` fitted into the
    canvas of the Android file: uniformly reduced if they are bigger, centred if smaller."""
    sw = entries_by_base(donor.get("data/System/systemTexture.pck"))
    out = {}
    for path in AT_FILES:
        orig = assets.read(path)
        if orig is None:
            continue
        o_im = Image.open(io.BytesIO(orig))
        new = swimages.decode(sw[base_name(path)])
        if new.width > o_im.width or new.height > o_im.height:
            k = min(o_im.width / new.width, o_im.height / new.height)
            new = new.resize((max(1, round(new.width * k)), max(1, round(new.height * k))), Image.LANCZOS)
        canvas = Image.new("RGBA", o_im.size, (0, 0, 0, 0))
        canvas.alpha_composite(new, ((o_im.width - new.width) // 2, (o_im.height - new.height) // 2))
        out[path] = sprites.encode_webp_exact(canvas)
    return out


def look_images(assets: AndroidAssets, donor: Donor) -> dict[str, dict[str, bytes]]:
    """The LOOK sprites: ``{package: {entry key: bytes}}`` for ``tap_to_quest`` (corner indicator) and ``tap_to_quest_s`` (centre notice)."""
    sw = entries_by_base(donor.get("data/System/systemTexture.pck"))
    a1 = entries_by_base(assets.read("data/System/systemTexture.pck"))
    a3 = entries_by_base(assets.read(ATLAS_PACK))
    letters = Image.open(io.BytesIO(sw["tap_to_look.webp"])).convert("RGBA")
    big, small = sprites.look_sprites(letters, swimages.decode(a1["tap_to_quest.webp"]), swimages.decode(a3["tap_to_quest_s.webp"]))
    return {"data/System/systemTexture.pck": {"tap_to_quest.webp": sprites.encode_webp_exact(big)},
            ATLAS_PACK: {"tap_to_quest_s.webp": sprites.encode_webp_exact(small)}}


# ------------------------------------------------------------------ merge --

def merge_package(android_blob: bytes, switch_blob: bytes | None, gen: dict[str, bytes], label: str, only_gen: bool = False) -> tuple[bytes, dict]:
    """The Android package with its pictures replaced: by ``gen`` first (by entry base name) and then by the Switch picture of the same name."""
    data0, ents = pck.read_pck(android_blob)
    sw = entries_by_base(switch_blob) if (switch_blob and not only_gen) else {}
    stat = defaultdict(int)
    skipped = []
    for e in ents:
        b = base_name(pck.entry_name(e[0]))
        if b in gen:
            e[1] = gen[b]
            stat["generated"] += 1
        elif b in sw and sw[b] != e[1]:
            da, ds = dims(e[1]), dims(sw[b])
            if da == ds:
                e[1] = sw[b]
                stat["switch"] += 1
            elif da and ds and not (da[0] >= SHEET_MIN[0] and da[1] >= SHEET_MIN[1]):
                e[1] = sw[b]
                stat["switch_other_size"] += 1
            else:
                stat["kept"] += 1
                skipped.append(f"{b} {da}->{ds}")
        else:
            stat["kept"] += 1
    stat["skipped"] = skipped
    return pck.write_pck(data0, ents, align=4), dict(stat)


def build(pack: LangPack, assets: AndroidAssets, donor: Donor, atlas_pck: bytes | None, say=print) -> dict[str, bytes]:
    """Every picture file the Android containers must get: ``{path inside the containers: new bytes}``.

    ``atlas_pck`` is the extended font atlas package from :func:`riviera.font.make_atlas` (languages with accents), or ``None``."""
    warnings: list[str] = []
    repl: dict[str, bytes] = {}

    # 1. whole files from the Switch dump (English, or translated)
    skip = set(EXCLUSIVE_PACKS) | set(EXCLUSIVE_FILES) | {ATLAS_PACK}
    for p in sorted(donor.english_paths() - skip):
        repl[p] = donor.get(p)
    for p, blob in donor.translated.items():
        if p not in skip and (p in repl or assets.has(p)):
            repl[p] = blob
    say(f"  {len(repl)} whole files from the Switch dump")

    # 2. the pictures that only exist in some form in Android: the pack's own, those derived from Switch's, the code-made ones
    own, warn = pack_images(pack, assets)
    warnings += warn
    derived, warn, _ = derived_images(assets, donor, say)
    warnings += warn
    code: dict[str, dict[str, bytes]] = defaultdict(dict)
    for path, blob in at_images(assets, donor).items():
        code[path]["*"] = blob
    for package, entries in look_images(assets, donor).items():
        code[package].update(entries)

    def layered(package: str) -> dict[str, bytes]:
        merged = dict(derived.get(package, {}))
        merged.update(own.get(package, {}))
        merged.update(code.get(package, {}))
        return merged

    packages = sorted((set(EXCLUSIVE_PACKS) | set(derived) | set(own) | set(code)) - {ATLAS_PACK})
    for package in packages:
        gen = layered(package)
        if not package.endswith(".pck"):                        # a loose picture: the new one replaces the whole file
            if "*" in gen:
                repl[package] = gen["*"]
            continue
        android_blob = assets.read(package)
        if android_blob is None:
            warnings.append(f"{package}: not in the app")
            continue
        switch_blob = donor.get(package)
        repl[package], stat = merge_package(android_blob, switch_blob, gen, package)
        say(f"  {package}: {stat.get('generated', 0)} drawn or adjusted, {stat.get('switch', 0)} from Switch, "
            f"{stat.get('switch_other_size', 0)} from Switch at another size, {stat.get('kept', 0)} kept")
        if stat["skipped"]:
            say("    big pictures with another size, kept: " + "; ".join(stat["skipped"]))

    # 3. the atlas and touch-button package: the font atlas (accented languages) and the pictures of the pack and the code
    blob = assets.read(ATLAS_PACK)
    data0, ents = pck.read_pck(blob)
    names = pck.names(ents)
    if atlas_pck is not None:
        _, new_ents = pck.read_pck(atlas_pck)
        new_names = pck.names(new_ents)
        for n in font.ATLASES:
            ents[names.index(n)][1] = new_ents[new_names.index(n)][1]
    gen = layered(ATLAS_PACK)
    atlas_lower = {n.lower() for n in font.ATLASES}
    for e in ents:
        nm = base_name(pck.entry_name(e[0]))
        if nm in gen and nm not in atlas_lower:
            e[1] = gen[nm]
    repl[ATLAS_PACK] = pck.write_pck(data0, ents, align=4)

    for w in warnings[:30]:
        say(f"  warning: {w}")
    return repl
