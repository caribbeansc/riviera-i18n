"""Synthetic game files for the tests. Nothing here comes from the game: a tiny NSO with a text table, a font string and
metrics, a ``data.bin`` / ``data_en.bin`` pair with a font atlas and a package of pictures, and a language pack to go with them.
They follow the same layouts the real files do, so the tests exercise the real code paths.
"""

from __future__ import annotations

import io
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from riviera import builds, font, packs, pck
from riviera.sge import obfuscate, pad4

# ------------------------------------------------------------- containers ---


def build_container(files: dict[str, bytes], compress: bool = True) -> bytes:
    """A ``data*.bin`` container holding ``files`` (all paths under one top-level folder, like ``data/...``)."""
    root: dict = {}
    for path, data in files.items():
        parts = path.split("/")
        d = root
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = data
    names, name_pos = bytearray(), {}

    def nm(s: str) -> int:
        if s not in name_pos:
            name_pos[s] = len(names)
            names.extend(s.encode("latin-1") + b"\0")
        return name_pos[s]

    top_name, top = next(iter(root.items()))
    entries = [[nm(top_name), 0, 0]]
    queue = [(0, top)]
    blobs, pos = [], 0
    while queue:
        idx, node = queue.pop(0)
        kids = sorted(node.items())
        first = len(entries)
        entries[idx][1] = 0x80000000 | len(kids)
        entries[idx][2] = first * 12
        for name, _ in kids:
            entries.append([nm(name), 0, 0])
        for k, (name, val) in enumerate(kids):
            e = first + k
            if isinstance(val, dict):
                queue.append((e, val))
                continue
            payload, flag = val, 0
            if compress:
                payload, flag = struct.pack("<I", len(val)) + zlib.compress(val), 0x40000000
            blob = obfuscate(payload, name)
            entries[e][1] = flag | len(blob)
            entries[e][2] = pos
            blobs.append(pad4(blob))
            pos += len(blobs[-1])
    ent = b"".join(struct.pack("<III", *e) for e in entries)
    index = struct.pack("<II", len(ent), len(names)) + ent + bytes(names)
    header = obfuscate(pad4(struct.pack("<I", len(index)) + zlib.compress(index)), "InfoData")
    return struct.pack("<ii", len(header), pos) + header + b"".join(blobs)


def make_pck(entries: dict[str, bytes]) -> bytes:
    data0 = 8 + len(entries) * pck.ENTRY
    return pck.write_pck(data0, [[n.encode("latin-1").ljust(64, b"\0"), b] for n, b in entries.items()])


def webp(size=(8, 8), color=(255, 0, 0, 255), lossless=True) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "WEBP", lossless=lossless, quality=100)
    return buf.getvalue()


# -------------------------------------------------------------------- NSO ---

TEXT_END, RODATA, DATA = 0x1000, 0x1000, 0x7000
CHARSET_AT = 0x1000                 # the font string
TABLE_AT = 0x4000                   # metrics tables (in rodata)
STRINGS_AT = 0x4800                 # the script's strings
SLOTS_AT = 0x7100                   # the text table
DESC_AT = 0x7000                    # block descriptors
METRIC_SLOTS = (0x7f00, 0x7f08, 0x7f10)
PROTECTED = "/"                     # a string only the code uses
IMAGE_END = 0x8000


@dataclass
class SynthNso:
    image: bytes
    build: builds.SwitchBuild
    rows: list[dict]               # block, row, en, jp
    charset: str
    protected_addr: int
    path: Path | None = None


def _adrp(rd: int, pc: int, target: int) -> int:
    imm = ((target & ~0xfff) - (pc & ~0xfff)) >> 12
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7ffff) << 5) | rd


def _add_imm(rd: int, rn: int, imm: int) -> int:
    return 0x91000000 | (imm << 10) | (rn << 5) | rd


def charset_string() -> str:
    """A 2494-character font string with the layout the real one has: full-width ASCII from cell 251, the native accents
    in the Latin-1 ranges, ``Þ`` and ``Ð`` in cells that can be taken over, a filler for the rest."""
    s = ["　"] * 2494
    for k in range(94):
        s[251 + k] = chr(0xFF01 + k)
    for k, ch in enumerate(font.NATIVE):
        s[2204 + k] = ch
    s[2230], s[2231] = "Þ", "Ð"
    return "".join(s)


def make_nso(blocks: list[dict]) -> SynthNso:
    """Build the memory image of an NSO whose table has ``blocks``.

    Each block is ``{"header": bool, "en": [...], "jp": [...], "kr": [...], "tc": [...]}`` with lists of the same length.
    """
    mem = bytearray(IMAGE_END)
    relocs: list[tuple[int, int]] = []                              # (address of pointer, target)

    # strings
    pos = STRINGS_AT
    addr_of: dict[str, int] = {}

    def string(s: str) -> int:
        nonlocal pos
        if s not in addr_of:
            data = s.encode("utf-8")
            mem[pos:pos + len(data)] = data
            addr_of[s] = pos
            pos += len(data) + 1
        return addr_of[s]

    empty = string("")
    prot = string(PROTECTED)

    # the text table and its descriptors
    slot = SLOTS_AT
    index = 0
    rows, desc = [], DESC_AT
    for bi, b in enumerate(blocks):
        n = len(b["en"])
        if b.get("header"):
            head_index = index
            for _ in range(4):
                relocs.append((slot, empty)); slot += 8; index += 1
            relocs.append((desc, SLOTS_AT + 8 * head_index))            # pointer to the header
        en_index = index
        for lang in ("en", "jp", "kr", "tc"):
            for text in b[lang]:
                relocs.append((slot, string(text))); slot += 8; index += 1
        for q in range(4):                                            # four pointers with a constant stride: the block
            relocs.append((desc + 0x10 + 8 * q, SLOTS_AT + 8 * (en_index + q * n)))
        desc += 0x40
        for k in range(n):
            rows.append({"block": bi, "row": k, "en": b["en"][k], "jp": b["jp"][k]})

    # font string and metrics tables
    charset = charset_string()
    cs = charset.encode("utf-8")
    mem[CHARSET_AT:CHARSET_AT + len(cs)] = cs
    spans = ((251, 332), (2204, 2261), (2378, 2386))
    tab = TABLE_AT
    for (lo, hi), mslot in zip(spans, METRIC_SLOTS):
        relocs.append((mslot, tab))
        for i in range(lo, hi + 1):
            struct.pack_into("<HHH", mem, tab, 1, 20 + (i % 7), 0)         # x0, width, y offset
            tab += 6
    assert tab < STRINGS_AT and CHARSET_AT + len(cs) < TABLE_AT, "synthetic layout overlap"

    # code: an `adrp`+`add` that uses the protected string directly
    code_at = 0x800
    struct.pack_into("<II", mem, code_at, _adrp(0, code_at, prot), _add_imm(0, 0, prot & 0xfff))

    # MOD0 / dynamic / RELA
    mod0, dyn, rela = 0x100, 0x140, 0x200
    struct.pack_into("<I", mem, 4, mod0)
    mem[mod0:mod0 + 4] = b"MOD0"
    struct.pack_into("<i", mem, mod0 + 4, dyn - mod0)
    struct.pack_into("<qQ", mem, dyn, 7, rela)
    struct.pack_into("<qQ", mem, dyn + 16, 8, 24 * len(relocs))
    struct.pack_into("<qQ", mem, dyn + 32, 0, 0)
    assert rela + 24 * len(relocs) <= 0x1000, "too many relocations for the synthetic text segment"
    for i, (p, target) in enumerate(relocs):
        struct.pack_into("<QQq", mem, rela + 24 * i, p, builds_R, target)
        struct.pack_into("<Q", mem, p, target)                       # the in-place value, like a prelinked file

    header = bytearray(0x100)
    header[:4] = b"NSO0"
    struct.pack_into("<III", header, 0x10, 0x100, 0, TEXT_END)               # text   (file offset, memory offset, size)
    struct.pack_into("<III", header, 0x20, 0x100 + TEXT_END, RODATA, DATA - RODATA)
    struct.pack_into("<III", header, 0x30, 0x100 + DATA, DATA, IMAGE_END - DATA)
    build_id = bytes.fromhex("AB" * 20) + bytes(12)
    header[0x40:0x60] = build_id
    image = bytes(header) + bytes(mem)
    build = builds.SwitchBuild(
        title_id="0100000000000000", version="synthetic", build_id=build_id[:20].hex().upper(), charset_addr=CHARSET_AT,
        metric_tables=tuple((s, lo, hi) for s, (lo, hi) in zip(METRIC_SLOTS, spans)),
        font_tables=tuple((s, lo, hi) for s, (lo, hi) in list(zip(METRIC_SLOTS, spans))[1:]))
    return SynthNso(image=image, build=build, rows=rows, charset=charset, protected_addr=prot)


builds_R = 1027                      # R_AARCH64_RELATIVE


def write_nso(path: Path, nso: SynthNso, compress: bool = False) -> Path:
    """Write ``nso`` as an NSO file (segments stored as they are)."""
    img = nso.image
    segs = [(0, TEXT_END), (RODATA, DATA - RODATA), (DATA, IMAGE_END - DATA)]
    out = bytearray(img[:0x100])
    offsets = []
    for mo, size in segs:
        offsets.append(len(out))
        out += img[0x100 + mo:0x100 + mo + size]
    for i, (mo, size) in enumerate(segs):
        struct.pack_into("<III", out, 0x10 + 0x10 * i, offsets[i], mo, size)
    struct.pack_into("<I", out, 0x0C, 0)
    Path(path).write_bytes(bytes(out))
    return Path(path)


# ---------------------------------------------------------- dump and pack ---

def atlas_pck(charset: str) -> bytes:
    """A ``systemTexture3.pck`` with two 37-row atlases whose base-letter cells have something drawn in them."""
    imgs = {}
    wanted = list(font.BASE.values()) + list(font.FLIP.values())
    idx_of = {ch: i for i, ch in enumerate(charset[:2134]) if ch != "　"}
    for name in font.ATLASES:
        im = Image.new("RGBA", (font.COLS * font.CELL, font.ORIG_ROWS * font.CELL), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for ch in set(wanted):
            r, c = divmod(idx_of[ch], font.COLS)
            x, y = c * font.CELL, r * font.CELL
            d.rectangle([x + 20, y + 20, x + 44, y + 60], fill=(255, 255, 255, 255))
        buf = io.BytesIO()
        im.save(buf, "WEBP", lossless=True, quality=100)
        imgs[name] = buf.getvalue()
    imgs["other.webp"] = webp()
    return make_pck(imgs)


def make_dump(root: Path, blocks: list[dict]) -> tuple[Path, Path, SynthNso]:
    """Write ``root/exefs/main`` and ``root/romfs/{data,data_en}.bin`` for a synthetic game; returns ``(exefs, romfs, nso)``."""
    nso = make_nso(blocks)
    exefs, romfs = Path(root) / "exefs", Path(root) / "romfs"
    exefs.mkdir(parents=True)
    romfs.mkdir(parents=True)
    write_nso(exefs / "main", nso)
    (romfs / "data.bin").write_bytes(build_container({"data/System/systemTexture3.pck": atlas_pck(nso.charset),
                                                      "data/readme.txt": b"hello"}))
    (romfs / "data_en.bin").write_bytes(build_container({
        "data/event/demo.pck": make_pck({"story_00.webp": webp((16, 8), (10, 20, 30, 255)),
                                         "panel.webp": webp((16, 8), (200, 200, 200, 255)),
                                         "keep.webp": webp((4, 4))}),
        "data/readme.txt": b"hi"}))
    return exefs, romfs, nso


def make_lang(langs: Path, code: str, text: dict[str, list[str]], *, soft: float = 1.4, images: bool = True,
              meta: dict | None = None) -> packs.LangPack:
    """Write ``langs/<code>/`` with ``text`` (``{raw English: translated segments}``) and, optionally, two pictures."""
    folder = Path(langs) / code
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"code": code, "name": code.upper(), "english_name": code, "mod_name": f"Test_{code.upper()}",
            "font": {"accents": True}, "platforms": {"switch": {"soft": soft}, "android": {}},
            "validation": {"extra_chars": "áéíóúÁÉÍÓÚñÑüÜ¡¿…"}, **(meta or {})}
    (folder / "lang.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    packs.write_jsonl(folder / "text.jsonl", ({"k": packs.fingerprint(en), "t": t} for en, t in sorted(text.items())))
    if images:
        from riviera import images as img
        base_dir = folder / "images" / "data_en" / "data" / "event" / "demo.pck"
        base_dir.mkdir(parents=True)
        original = webp((16, 8), (10, 20, 30, 255))
        (base_dir / "story_00.webp").write_bytes(webp((40, 12), (255, 255, 255, 255)))
        panel = img.decode(webp((16, 8), (200, 200, 200, 255)))
        edited = panel.copy()
        edited.paste((0, 0, 0, 255), (2, 2, 6, 6))
        overlay, mask, _ = img.make_delta(panel, edited)
        overlay.save(base_dir / "panel.png")
        mask.save(base_dir / "panel.mask.png")
        manifest = {"format": 1, "containers": {"data_en.bin": {"data/event/demo.pck": {
            "story_00.webp": {"kind": "full", "file": "data_en/data/event/demo.pck/story_00.webp", "base": img.sha1(original)},
            "panel.webp": {"kind": "delta", "overlay": "data_en/data/event/demo.pck/panel.png",
                           "mask": "data_en/data/event/demo.pck/panel.mask.png", "base": img.sha1(webp((16, 8), (200, 200, 200, 255)))},
        }}}}
        (folder / "images" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return packs.load_pack(folder)


# a small script: block 0 has a header, block 1 does not; block 1 is "dialogue" in no way (it is a UI block, 0-9)
def sample_blocks() -> list[dict]:
    en0 = ["Hello", "V(112b_0000)How are you today,V(112b_0001)friend?", "Press the B1 Button"]
    en1 = ["Yes", "No"]
    return [{"header": True, "en": en0, "jp": ["あ"] * 3, "kr": ["가"] * 3, "tc": ["甲"] * 3},
            {"header": False, "en": en1, "jp": ["はい", "いいえ"], "kr": ["예", "아니요"], "tc": ["是", "否"]}]
