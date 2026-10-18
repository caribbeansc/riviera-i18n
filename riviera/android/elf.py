"""Just enough ELF (64-bit little endian) to patch a shared library in place.

The Android build edits ``libapp.so``: it redirects string pointers (``R_AARCH64_RELATIVE``
relocations), patches a few instructions and appends one loadable segment. This module reads the
program headers, translates addresses to file offsets, lists the relocations and writes the new
segment. It does not interpret sections or symbols.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import AndroidError

PT_LOAD, PT_DYNAMIC, PT_NOTE = 1, 2, 4
PF_X, PF_W, PF_R = 1, 2, 4
DT_RELA, DT_RELASZ = 7, 8
R_AARCH64_RELATIVE = 1027
RELA_SIZE = 24                      # u64 slot, u64 info, i64 addend
SEGMENT_ALIGN = 0x4000              # alignment of the segment the build appends (16 KB pages)

PHDR = struct.Struct("<IIQQQQQQ")   # type, flags, offset, vaddr, paddr, filesz, memsz, align


class ElfError(AndroidError):
    """The file is not the kind of library this module understands."""


@dataclass
class Phdr:
    index: int
    at: int                         # file offset of the header itself
    type: int
    flags: int
    offset: int
    vaddr: int
    paddr: int
    filesz: int
    memsz: int
    align: int


class Elf:
    """A library held in memory as a ``bytearray`` (every write goes straight to :attr:`data`)."""

    def __init__(self, data):
        self.data = bytearray(data)
        d = self.data
        if d[:4] != b"\x7fELF" or d[4] != 2 or d[5] != 1:
            raise ElfError("not a 64-bit little-endian ELF file")
        self.phoff, = struct.unpack_from("<Q", d, 0x20)
        self.phentsize, self.phnum = struct.unpack_from("<HH", d, 0x36)
        self.phdrs = [Phdr(i, self.phoff + i * self.phentsize, *PHDR.unpack_from(d, self.phoff + i * self.phentsize))
                      for i in range(self.phnum)]

    # ----------------------------------------------------------- addresses --
    @property
    def loads(self) -> list[Phdr]:
        return [p for p in self.phdrs if p.type == PT_LOAD]

    def file_offset(self, vaddr: int) -> int:
        """File offset of a virtual address, which must lie in the file-backed part of a loadable segment."""
        for p in self.loads:
            if p.vaddr <= vaddr < p.vaddr + p.filesz:
                return vaddr - p.vaddr + p.offset
        raise ElfError(f"address 0x{vaddr:x} is not in the file image")

    def vaddr_of(self, offset: int) -> int:
        """Virtual address of a file offset (the inverse of :meth:`file_offset`)."""
        for p in self.loads:
            if p.offset <= offset < p.offset + p.filesz:
                return offset - p.offset + p.vaddr
        raise ElfError(f"file offset 0x{offset:x} is not loaded")

    def memory_end(self) -> int:
        """First virtual address after every loadable segment."""
        return max(p.vaddr + p.memsz for p in self.loads)

    def memory_image(self, limit: int | None = None) -> bytes:
        """The loaded image (what the process sees at ``vaddr``), zero-filled between segments."""
        top = max(p.vaddr + p.memsz for p in self.loads)
        mem = bytearray(top if limit is None else min(top, limit))
        for p in self.loads:
            chunk = self.data[p.offset:p.offset + p.filesz]
            if p.vaddr < len(mem):
                mem[p.vaddr:p.vaddr + len(chunk)] = chunk[:len(mem) - p.vaddr]
        return bytes(mem)

    def read(self, vaddr: int, size: int) -> bytes:
        o = self.file_offset(vaddr)
        return bytes(self.data[o:o + size])

    def write(self, vaddr: int, payload: bytes) -> None:
        o = self.file_offset(vaddr)
        self.data[o:o + len(payload)] = payload

    def u32(self, vaddr: int) -> int:
        return struct.unpack("<I", self.read(vaddr, 4))[0]

    # -------------------------------------------------------- relocations --
    def dynamic_tags(self) -> dict[int, int]:
        dyn = next((p for p in self.phdrs if p.type == PT_DYNAMIC), None)
        if dyn is None:
            raise ElfError("no dynamic section")
        tags: dict[int, int] = {}
        o = dyn.offset
        while o + 16 <= dyn.offset + dyn.filesz:
            tag, value = struct.unpack_from("<qQ", self.data, o)
            o += 16
            if tag == 0:
                break
            tags.setdefault(tag, value)
        return tags

    def relative_relocs(self) -> dict[int, tuple[int, int]]:
        """``{address of the pointer: (file offset of its RELA entry, address it points to)}`` for the RELATIVE entries."""
        tags = self.dynamic_tags()
        if DT_RELA not in tags or DT_RELASZ not in tags:
            raise ElfError("no RELA relocations")
        start = self.file_offset(tags[DT_RELA])
        out = {}
        for o in range(start, start + tags[DT_RELASZ], RELA_SIZE):
            slot, info, addend = struct.unpack_from("<QQq", self.data, o)
            if info & 0xFFFFFFFF == R_AARCH64_RELATIVE:
                out[slot] = (o, addend)
        return out

    def set_pointer(self, slot: int, rela_offset: int, target: int) -> None:
        """Point ``slot`` at ``target``: the addend of its relocation (what the loader applies) and the value stored in the file."""
        struct.pack_into("<q", self.data, rela_offset + 16, target)
        struct.pack_into("<Q", self.data, self.file_offset(slot), target)

    # -------------------------------------------------------------- segment --
    def next_segment_address(self, align: int = SEGMENT_ALIGN) -> tuple[int, int]:
        """``(file offset, virtual address)`` where a segment appended to the file goes: the end of the file and the end of the
        loaded image, both rounded up to ``align`` (and one page apart in memory, as the original build of the segment did)."""
        offset = -(-len(self.data) // align) * align
        vaddr = -(-self.memory_end() // align) * align + align
        return offset, vaddr

    def replace_note_with_load(self, offset: int, vaddr: int, size: int, flags: int, align: int) -> None:
        """Turn the ``PT_NOTE`` header into a ``PT_LOAD`` for the appended segment (the header table has no spare room)."""
        note = next((p for p in self.phdrs if p.type == PT_NOTE), None)
        if note is None:
            raise ElfError("no PT_NOTE header to reuse for the new segment")
        PHDR.pack_into(self.data, note.at, PT_LOAD, flags, offset, vaddr, vaddr, size, size, align)
        note.type, note.flags, note.offset, note.vaddr, note.paddr = PT_LOAD, flags, offset, vaddr, vaddr
        note.filesz = note.memsz = size
        note.align = align

    def set_segment_flags(self, phdr: Phdr, flags: int) -> None:
        struct.pack_into("<I", self.data, phdr.at + 4, flags)
        phdr.flags = flags
