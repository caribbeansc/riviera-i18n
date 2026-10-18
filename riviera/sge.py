"""The ``data*.bin`` containers of the game (Sting's ``sge`` engine).

The same format is used by the Switch, PC and Android builds. It was read off
``sge::Resource`` in the Android library.

Layout::

    u32 header_size, u32 data_size
    header (header_size bytes) = XOR-obfuscated  u32 size + zlib(index)
    file data, each file obfuscated with its own key

* **Obfuscation:** XOR by 32-bit words with ``MD5(rot13(name))``, word *i* using
  key word ``i & 3``. The index uses the name ``"InfoData"``; each file, its own
  file name without the path.
* **Index:** ``u32 names_off, u32 names_size`` and then 12-byte entries
  ``(u32 name_off, u32 info, u32 value)``; the names live at ``8 + names_off``.
  With bit 31 of ``info`` set an entry is a directory of ``info & 0x3fffffff``
  children whose first one sits ``value`` bytes from the start of the entries.
  Otherwise it is a file of ``info & 0x3fffffff`` bytes at ``8 + header_size +
  value``; bit 30 means the file is further wrapped as ``u32 size + zlib``.
  Offsets are aligned to 4.
"""

from __future__ import annotations

import codecs
import hashlib
import os
import struct
import zlib
from collections.abc import Mapping
from pathlib import Path


def obfus_key(name: str) -> bytes:
    return hashlib.md5(codecs.encode(name, "rot13").encode("latin-1")).digest()


def deobfuscate(data: bytes, name: str) -> bytes:
    """XOR with the key of ``name``. The operation is its own inverse."""
    pad = (-len(data)) % 4
    buf = data + b"\0" * pad
    k = struct.unpack("<4I", obfus_key(name))
    words = struct.unpack(f"<{len(buf) // 4}I", buf)
    out = struct.pack(f"<{len(words)}I", *(w ^ k[i & 3] for i, w in enumerate(words)))
    return out[:len(data)]


obfuscate = deobfuscate


def pad4(b: bytes) -> bytes:
    return b + b"\0" * ((-len(b)) % 4)


class Archive:
    """Read access to one container."""

    def __init__(self, path):
        self.path = Path(path)
        self.f = open(path, "rb")
        self.header_size, self.data_size = struct.unpack("<ii", self.f.read(8))
        raw = deobfuscate(self.f.read(self.header_size), "InfoData")
        self.index = zlib.decompress(raw[4:])
        self.names_off, self.names_size = struct.unpack_from("<II", self.index)

    def close(self) -> None:
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def entry(self, byte_off: int) -> tuple[int, int, int]:
        return struct.unpack_from("<III", self.index, 8 + byte_off)

    def name(self, off: int) -> str:
        start = 8 + self.names_off + off
        return self.index[start:self.index.index(b"\0", start)].decode("latin-1")

    def walk(self, byte_off: int = 0, prefix: str = ""):
        """Yield ``(path, name, info, value)`` for every file."""
        name_off, info, value = self.entry(byte_off)
        name = self.name(name_off)
        path = f"{prefix}/{name}" if prefix else name
        if info & 0x80000000:
            for i in range(info & 0x3FFFFFFF):
                yield from self.walk(value + 12 * i, path)
        else:
            yield path, name, info, value

    def read(self, name: str, info: int, value: int) -> bytes:
        self.f.seek(8 + self.header_size + value)
        data = deobfuscate(self.f.read(info & 0x3FFFFFFF), name)
        if info & 0x40000000:
            data = zlib.decompress(data[4:])
        return data

    def paths(self) -> list[str]:
        return [p for p, *_ in self.walk()]

    def read_path(self, path: str) -> bytes:
        for p, name, info, value in self.walk():
            if p == path:
                return self.read(name, info, value)
        raise KeyError(path)


def extract(archive: str, out_dir: str, only=None) -> int:
    """Write every file (or the ones ``only`` accepts) under ``out_dir``. Returns the count."""
    n = 0
    with Archive(archive) as arc:
        for path, name, info, value in arc.walk():
            if only and not only(path):
                continue
            dest = os.path.join(out_dir, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(arc.read(name, info, value))
            n += 1
    return n


def pack(src, repl, dst) -> int:
    """Rebuild a container, replacing files. Returns how many were replaced.

    The index keeps the original structure and files that are not replaced are
    copied as they are (still obfuscated). Replacements are compressed with zlib
    and obfuscated with the key of their name, the way the originals are.

    ``repl`` is a mapping ``{path inside the container: new bytes}``, a folder, or
    a list of folders (the first one that has the file wins) laid out like the
    output of :func:`extract` (for example ``data/event/e_00.pck``).
    """
    if isinstance(repl, Mapping):
        def find(path):
            return repl.get(path)
    else:
        dirs = [repl] if isinstance(repl, (str, os.PathLike)) else list(repl)

        def find(path):
            for d in dirs:
                p = os.path.join(d, path)
                if os.path.isfile(p):
                    return open(p, "rb").read()
            return None

    arc = Archive(src)
    index = bytearray(arc.index)
    blobs: list[bytes] = []
    pos = 0
    replaced = 0

    def visit(byte_off: int, prefix: str) -> None:
        nonlocal pos, replaced
        name_off, info, value = arc.entry(byte_off)
        name = arc.name(name_off)
        path = f"{prefix}/{name}" if prefix else name
        if info & 0x80000000:
            for i in range(info & 0x3FFFFFFF):
                visit(value + 12 * i, path)
            return
        plain = find(path)
        if plain is not None:
            payload = struct.pack("<I", len(plain)) + zlib.compress(plain, 9)
            data = obfuscate(payload, name)
            info = 0x40000000 | len(data)
            replaced += 1
        else:
            arc.f.seek(8 + arc.header_size + value)
            data = arc.f.read(info & 0x3FFFFFFF)
        struct.pack_into("<II", index, 8 + byte_off + 4, info, pos)
        blobs.append(pad4(data))
        pos += len(blobs[-1])

    visit(0, "")
    payload = struct.pack("<I", len(index)) + zlib.compress(bytes(index), 9)
    header = obfuscate(pad4(payload), "InfoData")
    with open(dst, "wb") as out:
        out.write(struct.pack("<ii", len(header), pos))
        out.write(header)
        for b in blobs:
            out.write(b)
    arc.close()
    return replaced
