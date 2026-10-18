"""Tests of riviera.android.elf on a small synthetic library (no game files)."""

import struct

import pytest

from riviera.android import elf as elfmod
from riviera.android.elf import Elf, ElfError


def make_library(*, strings=(), words=None, relocs=(), tail=0):
    """A minimal 64-bit ELF with a text/rodata segment, a data segment holding a RELA table and a PT_NOTE to reuse.

    ``strings``: NUL-terminated byte strings placed in the first segment (their addresses are returned).
    ``words``: ``{address: 4 bytes}`` written in the first segment. ``relocs``: ``[(slot index, string index)]`` RELATIVE relocations
    whose slots are consecutive 8-byte cells of the data segment. Returns ``(bytes, info)``."""
    text_va, text_off = 0x1000, 0x1000
    body = bytearray(0x1000)                     # the first segment is one page; the strings start at +0x200
    addrs, pos = [], 0x200
    for s in strings:
        body[pos:pos + len(s) + 1] = s + b"\0"
        addrs.append(text_va + pos)
        pos += len(s) + 1
    for a, w in (words or {}).items():
        body[a - text_va:a - text_va + 4] = w
    data_va, data_off = 0x3000, 0x2000
    rela_at = 0x100                              # RELA table at data_va + 0x100, the slots from data_va + 0x200
    data = bytearray(0x400)
    rela = bytearray()
    slots = []
    for i, (slot_i, str_i) in enumerate(relocs):
        slot = data_va + 0x200 + 8 * slot_i
        slots.append(slot)
        struct.pack_into("<Q", data, 0x200 + 8 * slot_i, addrs[str_i])
        rela += struct.pack("<QQq", slot, elfmod.R_AARCH64_RELATIVE, addrs[str_i])
    data[rela_at:rela_at + len(rela)] = rela
    dyn_at = 0x300
    dyn = struct.pack("<qQqQqQ", elfmod.DT_RELA, data_va + rela_at, elfmod.DT_RELASZ, len(rela), 0, 0)
    data[dyn_at:dyn_at + len(dyn)] = dyn
    phnum = 4
    header = bytearray(0x40 + phnum * 56)
    header[:4] = b"\x7fELF"
    header[4], header[5] = 2, 1
    struct.pack_into("<Q", header, 0x20, 0x40)
    struct.pack_into("<HH", header, 0x36, 56, phnum)
    ph = [(elfmod.PT_LOAD, elfmod.PF_R | elfmod.PF_X, text_off, text_va, text_va, len(body), len(body), 0x1000),
          (elfmod.PT_LOAD, elfmod.PF_R | elfmod.PF_W, data_off, data_va, data_va, len(data), len(data) + 0x100, 0x1000),
          (elfmod.PT_DYNAMIC, elfmod.PF_R | elfmod.PF_W, data_off + dyn_at, data_va + dyn_at, data_va + dyn_at, len(dyn), len(dyn), 8),
          (elfmod.PT_NOTE, elfmod.PF_R, 0x200, 0x200, 0x200, 0, 0, 4)]
    for i, p in enumerate(ph):
        elfmod.PHDR.pack_into(header, 0x40 + 56 * i, *p)
    out = bytearray(data_off + len(data) + tail)
    out[:len(header)] = header
    out[text_off:text_off + len(body)] = body
    out[data_off:data_off + len(data)] = data
    return bytes(out), {"strings": addrs, "slots": slots, "text_va": text_va, "data_va": data_va}


def test_rejects_other_files():
    with pytest.raises(ElfError):
        Elf(b"MZ" + bytes(100))


def test_addresses_and_image():
    lib, info = make_library(strings=[b"hello", b"world"], words={0x1100: b"\x01\x02\x03\x04"})
    e = Elf(lib)
    assert e.file_offset(0x1100) == 0x1100
    assert e.file_offset(0x3010) == 0x2010
    assert e.vaddr_of(0x2010) == 0x3010
    with pytest.raises(ElfError):
        e.file_offset(0x3000 + 0x400 + 0x10)           # in memory (bss) but not in the file
    mem = e.memory_image()
    assert mem[0x1100:0x1104] == b"\x01\x02\x03\x04"
    assert mem[info["strings"][1]:info["strings"][1] + 5] == b"world"
    assert e.read(0x1100, 4) == b"\x01\x02\x03\x04"
    e.write(0x1100, b"\xaa\xbb\xcc\xdd")
    assert e.u32(0x1100) == 0xddccbbaa


def test_relocations_and_set_pointer():
    lib, info = make_library(strings=[b"one", b"two"], relocs=[(0, 0), (1, 1)])
    e = Elf(lib)
    relocs = e.relative_relocs()
    assert set(relocs) == set(info["slots"])
    assert [relocs[s][1] for s in info["slots"]] == info["strings"]
    rela_off, _ = relocs[info["slots"][0]]
    e.set_pointer(info["slots"][0], rela_off, 0x123456)
    again = Elf(bytes(e.data)).relative_relocs()
    assert again[info["slots"][0]][1] == 0x123456
    assert struct.unpack("<Q", e.read(info["slots"][0], 8))[0] == 0x123456


def test_next_segment_address_is_aligned():
    """SPEC-014/R-2: the appended segment goes after the file and the image, both aligned."""
    lib, _ = make_library(tail=0x123)
    e = Elf(lib)
    off, va = e.next_segment_address()
    assert off % elfmod.SEGMENT_ALIGN == 0 and off >= len(lib)
    assert va % elfmod.SEGMENT_ALIGN == 0 and va > e.memory_end()


def test_note_becomes_the_new_load_segment():
    """SPEC-014/R-2: the PT_NOTE header is reused as the PT_LOAD of the appended segment (read and execute)."""
    lib, _ = make_library()
    e = Elf(lib)
    off, va = e.next_segment_address()
    e.data.extend(b"\0" * (off - len(e.data)) + b"payload!")
    e.replace_note_with_load(off, va, 8, elfmod.PF_R | elfmod.PF_X, elfmod.SEGMENT_ALIGN)
    again = Elf(bytes(e.data))
    seg = again.loads[-1] if again.loads[-1].vaddr == va else next(p for p in again.loads if p.vaddr == va)
    assert (seg.offset, seg.filesz, seg.flags) == (off, 8, elfmod.PF_R | elfmod.PF_X)
    assert again.read(va, 8) == b"payload!"
