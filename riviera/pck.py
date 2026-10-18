"""The ``.pck`` packages that sit inside the game's ``data*.bin`` containers.

A package is a tiny archive of images: ``u32 count``, ``u32 start of data`` and
one 72-byte entry per file (a 64-byte zero-padded name, ``u32 size``, ``u32
offset``), followed by the data back to back. The images inside are WebP with
alpha. The engine draws each one at its own native size, so an entry can be
replaced by an image of a different size.
"""

from __future__ import annotations

import struct

ENTRY = 0x48                    # 64-byte name + size + offset


def read_pck(data: bytes) -> tuple[int, list[list]]:
    """``(start of data, [[raw 64-byte name, blob], ...])`` in file order."""
    count, data0 = struct.unpack_from("<II", data, 0)
    entries = []
    for i in range(count):
        o = 8 + i * ENTRY
        size, off = struct.unpack_from("<II", data, o + 64)
        entries.append([data[o:o + 64], data[off:off + size]])
    return data0, entries


def write_pck(data0: int, entries: list[list], align: int = 1) -> bytes:
    """Inverse of :func:`read_pck`. ``align`` pads each blob (the Android build wants 4)."""
    head = bytearray(struct.pack("<II", len(entries), data0))
    body = bytearray()
    for name, blob in entries:
        head += name + struct.pack("<II", len(blob), data0 + len(body))
        body += blob
        if align > 1:
            body += b"\0" * ((-len(body)) % align)
    if len(head) != data0:
        raise ValueError(f"package header is {len(head)} bytes, expected {data0}")
    return bytes(head + body)


def entry_name(raw: bytes) -> str:
    return raw.split(b"\0")[0].decode("latin-1")


def names(entries: list[list]) -> list[str]:
    return [entry_name(e[0]) for e in entries]
