#!/usr/bin/env python3
"""Compile the proportional-text hooks (``hooks.c``) into the blob the Android build ships.

Development tool: it needs LLVM (``clang``, ``ld.lld``, ``llvm-objcopy``, ``llvm-nm``) and the *original* ``libapp.so`` of the
supported app version. Users never run it: ``python rpl.py android build`` only copies the result (``riviera/android/data/hooks.bin``
and ``hooks.json``) into the library.

The blob contains **code only**. Everything that belongs to the game is a hole the builder fills from the user's own files:

* the engine's metrics tables and character string (reserved, zero-filled, in the ``.tables`` section);
* the original instruction each hook displaces (a ``nop`` placeholder in the cave, listed in ``hooks.json``).

The library is pinned by its SHA-256, so every address in this file is a fact about one build. The expected original instructions are not
stored: ``hooks.json`` keeps a short fingerprint of ``address + word`` for each site, so a different build is refused before anything is written.

    python tools/android/build_hooks.py --lib libapp.so --llvm-bin /path/to/llvm/bin
    python tools/android/build_hooks.py --lib libapp.so --check          # rebuild and compare with the shipped files
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from riviera.android import hooks as rt            # noqa: E402  (the runtime half: fingerprints and branch encoding)
from riviera.android.elf import Elf                # noqa: E402

DATA = ROOT / "riviera" / "android" / "data"
FRAME = 0x130                                      # bytes a cave saves on the stack around the call into C
NOP = 0xD503201F

# Addresses of the game's own functions that the C code calls (link-time symbols).
GAME_SYMBOLS = {"GetFontSystemIndex": 0x58f95c, "GetUtf8Code": 0x58e974}

# "Cave" hooks. ``kind``: post = save registers, call the C hook, restore, run the displaced instruction, jump back;
# skip = the hook replaces the statement (the instruction at ``addr`` is not run; execution resumes at ``resume``);
# asm = a hand-written cave. ``resume`` is where the cave jumps back to (default: the instruction after ``addr``).
HOOKS = [
    dict(name="code_pos", addr=0x5909a8, kind="post", func="hk_code_pos"),
    dict(name="code_adv", addr=0x590b4c, kind="skip", func="hk_code_adv", resume=0x590b78),
    dict(name="sys_pos", addr=0x591974, kind="post", func="hk_sys_pos"),
    dict(name="sys_adv", addr=0x591ac8, kind="skip", func="hk_sys_adv", resume=0x591ae0),
    # pitch = max(pitch, 0) on entering FNT_setSystem (param_10 is at [x29,-0xcc]); the displaced instruction runs after it
    dict(name="sys_pitch", addr=0x5911d0, kind="asm"),
    # CConfMsg::disp: the first hook runs after the box's x is stored, the second before the patched `add w2, w8, w10`
    dict(name="conf_box", addr=0x7540f8, kind="post", func="hk_conf_box"),
    dict(name="conf_text", addr=0x75412c, kind="post", func="hk_conf_text"),
    # FNT_setCodeSub: replaces `fmov s0,#1.0` (the scale passed to FNT_setCode) by a scale that fits the page to the width
    dict(name="msg_scale", addr=0x58dac8, kind="skip", func="hk_msg_scale"),
]
# whole functions replaced by a jump to the hook: (address, symbol)
REPLACE = [(0x58eeb8, "hk_getwidth"), (0x58eab8, "hk_fontpitch")]

# one-instruction patches: (address, new word as 4 little-endian bytes in hex, what it does). The original word is checked by fingerprint.
PATCHES = [
    (0x590094, "0150241e", "FNT_setCode: U+3000 advances 9 * scale"),
    (0x58e8d4, "0150241e", "calcStringWidth: U+3000 advances 9 * scale"),
    (0x5917e4, "2905480b", "FNT_setSystem: U+3000 advances pitch + cell / 2"),
    (0x756d40, "82ed8052", "CDiff::disp: bottom note at x 0x76c instead of 0x5a8"),
    (0x756d50, "46008052", "CDiff::disp: bottom note flags 0 -> 2 (right aligned)"),
    (0x75410c, "a2435d78", "CConfMsg::disp: box width = the one hk_conf_box leaves at [x29,-0x2c]"),
    (0x754130, "02010a0b", "CConfMsg::disp: x of the text = box width / 2"),
]
# FNT_init loads the character string with `adrp x1, ...; add x1, x1, #...`: the builder points it at the extended one (accent fonts only)
INIT_CHARSET = dict(addr=0x58d0b4, reg=1)

SAVE = """
.macro SAVE
    sub sp, sp, #%(f)d
    stp x0, x1, [sp, #0x00]
    stp x2, x3, [sp, #0x10]
    stp x4, x5, [sp, #0x20]
    stp x6, x7, [sp, #0x30]
    stp x8, x9, [sp, #0x40]
    stp x10, x11, [sp, #0x50]
    stp x12, x13, [sp, #0x60]
    stp x14, x15, [sp, #0x70]
    stp x16, x17, [sp, #0x80]
    str x30, [sp, #0x90]
    stp q0, q1, [sp, #0xa0]
    stp q2, q3, [sp, #0xc0]
    stp q4, q5, [sp, #0xe0]
    stp q6, q7, [sp, #0x100]
.endm
.macro RESTORE
    ldp q6, q7, [sp, #0x100]
    ldp q4, q5, [sp, #0xe0]
    ldp q2, q3, [sp, #0xc0]
    ldp q0, q1, [sp, #0xa0]
    ldr x30, [sp, #0x90]
    ldp x16, x17, [sp, #0x80]
    ldp x14, x15, [sp, #0x70]
    ldp x12, x13, [sp, #0x60]
    ldp x10, x11, [sp, #0x50]
    ldp x8, x9, [sp, #0x40]
    ldp x6, x7, [sp, #0x30]
    ldp x4, x5, [sp, #0x20]
    ldp x2, x3, [sp, #0x10]
    ldp x0, x1, [sp, #0x00]
    add sp, sp, #%(f)d
.endm
""" % {"f": FRAME}


def caves_source() -> str:
    src = SAVE + "\n    .text\n    .balign 4\n"
    for h in HOOKS:
        n = h["name"]
        src += f"    .global cave_{n}\ncave_{n}:\n"
        if h["kind"] == "asm":
            src += (f"    ldur w8, [x29, #-0xcc]\n    tbz w8, #31, 1f\n    stur wzr, [x29, #-0xcc]\n1:\n"
                    f"    .global slot_{n}\nslot_{n}:\n    .inst 0x{NOP:08x}\n    b ORIG_{n}\n")
            continue
        src += f"    SAVE\n    add x0, sp, #{FRAME}\n    mov x1, x29\n    bl {h['func']}\n    RESTORE\n"
        if h["kind"] == "post":
            src += f"    .global slot_{n}\nslot_{n}:\n    .inst 0x{NOP:08x}\n"
        src += f"    b ORIG_{n}\n"
    return src


def run(cmd, **kw) -> str:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{r.stdout}{r.stderr}")
    return r.stdout


def c_define(name: str) -> int:
    """Value of ``#define name <integer>`` in hooks.c (the table geometry lives there, once)."""
    m = re.search(r"^#define\s+%s\s+(\d+)" % re.escape(name), Path(__file__).with_name("hooks.c").read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit(f"hooks.c has no #define {name}")
    return int(m.group(1))


def find_tool(name: str, llvm_bin: Path | None) -> str:
    if llvm_bin and (llvm_bin / name).exists():
        return str(llvm_bin / name)
    found = shutil.which(name)
    if not found:
        sys.exit(f"{name} not found: pass --llvm-bin or put LLVM on the PATH")
    return found


def build(lib: bytes, llvm_bin: Path | None) -> tuple[bytes, dict]:
    elf = Elf(lib)
    _, base = elf.next_segment_address()
    word = lambda a: elf.read(a, 4)                                   # noqa: E731

    clang, lld = find_tool("clang", llvm_bin), find_tool("ld.lld", llvm_bin)
    objcopy, nm = find_tool("llvm-objcopy", llvm_bin), find_tool("llvm-nm", llvm_bin)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "caves.S").write_text(caves_source(), encoding="utf-8")
        cflags = ["--target=aarch64-linux-gnu", "-O2", "-ffreestanding", "-fno-pic", "-fno-stack-protector", "-fno-builtin",
                  "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-ffixed-x18", "-ffp-contract=off", "-Wall", "-Werror"]
        run([clang, *cflags, "-c", Path(__file__).with_name("hooks.c"), "-o", td / "hooks.o"])
        run([clang, "--target=aarch64-linux-gnu", "-c", td / "caves.S", "-o", td / "caves.o"])
        (td / "link.ld").write_text(
            "SECTIONS {\n  . = 0x%x;\n  .text : { *(.text .text.*) }\n  .rodata : ALIGN(16) { *(.rodata .rodata.*) }\n"
            "  .tables : ALIGN(16) { *(.tables) }\n"
            "  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.ARM.attributes) *(.data*) *(.bss*) }\n}\n" % base)
        defs = [f"--defsym={n}=0x{a:x}" for n, a in GAME_SYMBOLS.items()]
        defs += [f"--defsym=ORIG_{h['name']}=0x{h.get('resume', h['addr'] + 4):x}" for h in HOOKS]
        run([lld, "-o", td / "blob.elf", "-T", td / "link.ld", "--no-rosegment", "-z", "norelro", "-e", "0", *defs,
             td / "hooks.o", td / "caves.o"])
        run([objcopy, "-O", "binary", td / "blob.elf", td / "blob.bin"])
        blob = (td / "blob.bin").read_bytes()
        syms = {}
        for line in run([nm, td / "blob.elf"]).splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)

    def off(sym: str) -> int:
        return syms[sym] - base

    tables = {}
    for name in ("M1", "M2", "M3"):
        first, count = c_define(f"{name}_FIRST"), c_define(f"{name}_COUNT")
        tables[name] = {"off": off(name), "first": first, "count": count, "size": 6 * count}
    tables["charset"] = {"off": off("charset_es"), "size": c_define("CHARSET_MAX")}
    for t in tables.values():                                           # the holes must be zero in the shipped blob
        if any(blob[t["off"]:t["off"] + t["size"]]):
            sys.exit("a table is not empty in the blob: game data would ship")

    hooks = []
    for h in HOOKS:
        n = h["name"]
        hooks.append({"name": n, "addr": h["addr"], "kind": h["kind"], "cave": off(f"cave_{n}"),
                      "slot": off(f"slot_{n}") if f"slot_{n}" in syms else None,
                      "orig": rt.site_fingerprint(h["addr"], word(h["addr"])),
                      "resume": h.get("resume"),
                      "resume_orig": rt.site_fingerprint(h["resume"], word(h["resume"])) if h.get("resume") else None})
    meta = {
        "version": 1,
        "library_sha256": hashlib.sha256(lib).hexdigest(),
        "base": base,
        "size": len(blob),
        "hooks": hooks,
        "replace": [{"addr": a, "to": off(s), "orig": rt.site_fingerprint(a, word(a)), "what": s} for a, s in REPLACE],
        "patches": [{"addr": a, "orig": rt.site_fingerprint(a, word(a)), "new": new, "what": what} for a, new, what in PATCHES],
        "tables": tables,
        "init_charset": {**INIT_CHARSET, "orig": rt.site_fingerprint(INIT_CHARSET["addr"], elf.read(INIT_CHARSET["addr"], 8))},
    }
    return blob, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lib", required=True, help="the original libapp.so of the supported app version")
    ap.add_argument("--llvm-bin", type=Path, default=Path(os.environ["LLVM_BIN"]) if os.environ.get("LLVM_BIN") else None)
    ap.add_argument("--out", type=Path, default=DATA)
    ap.add_argument("--check", action="store_true", help="rebuild and compare with the shipped files instead of writing them")
    a = ap.parse_args()
    blob, meta = build(Path(a.lib).read_bytes(), a.llvm_bin)
    text = json.dumps(meta, indent=1, sort_keys=True) + "\n"
    if a.check:
        same = (a.out / "hooks.bin").read_bytes() == blob and (a.out / "hooks.json").read_text(encoding="utf-8") == text
        print("up to date" if same else "DIFFERENT from the shipped files")
        return 0 if same else 1
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "hooks.bin").write_bytes(blob)
    (a.out / "hooks.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(blob)} bytes at 0x{meta['base']:x}; {len(meta['hooks'])} hooks, {len(meta['patches'])} patches -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
