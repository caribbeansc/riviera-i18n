"""Tests of riviera.android.arsc: renaming the app in a compiled resource table (SPEC-013/R-10), on synthetic tables."""

import hashlib
import struct

import pytest

from riviera.android import arsc


def encode(s: str, utf8: bool) -> bytes:
    assert len(s) < 128
    if utf8:
        b = s.encode("utf-8")
        return bytes([len(s.encode("utf-16-le")) // 2, len(b)]) + b + b"\0"
    u = s.encode("utf-16-le")
    return struct.pack("<H", len(u) // 2) + u + b"\0\0"


def make_table(strings, utf8=True, tail=b"PACKAGE-CHUNK-BYTES"):
    """A resource table with a global string pool of ``strings`` and a trailing blob standing for the packages."""
    enc = [encode(s, utf8) for s in strings]
    offs, pos = [], 0
    for e in enc:
        offs.append(pos)
        pos += len(e)
    area = b"".join(enc)
    area += b"\0" * ((-len(area)) % 4)
    start = 28 + 4 * len(strings)
    pool = struct.pack("<HHIIIIII", 1, 28, start + len(area), len(strings), 0, 0x100 if utf8 else 0, start, 0)
    pool += struct.pack(f"<{len(strings)}I", *offs) + area
    return struct.pack("<HHII", 2, 12, 12 + len(pool) + len(tail), 0) + pool + tail


def read_table(data):
    """``(strings, trailing bytes)`` read back with the rules of the format, independently of the module under test."""
    assert struct.unpack_from("<HH", data, 0) == (2, 12) and struct.unpack_from("<I", data, 4)[0] == len(data)
    p = 12
    _, _, size, count, styles, flags, start, _ = struct.unpack_from("<HHIIIIII", data, p)
    assert styles == 0 and start == 28 + 4 * count and size % 4 == 0
    offs = struct.unpack_from(f"<{count}I", data, p + 28)
    out = []
    for o in offs:
        q = p + start + o
        if flags & 0x100:
            q += 1                                                  # characters count (UTF-16 units), then the bytes count
            n = data[q]
            out.append(data[q + 1:q + 1 + n].decode("utf-8"))
        else:
            n, = struct.unpack_from("<H", data, q)
            out.append(data[q + 2:q + 2 + 2 * n].decode("utf-16-le"))
    return out, data[p + size:]


def sha(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("utf8", [True, False])
@pytest.mark.parametrize("new", ["Riviera", "X", "A much longer name for the application, with accents: áñ"])
def test_the_name_is_replaced_and_everything_else_stays(utf8, new):
    """SPEC-013/R-10: only the string with the fingerprint changes; the others keep their text, the offsets and sizes are corrected, and what follows is untouched."""
    strings = ["Alpha", "Old Name", "Gamma", "Ñandú"]
    data = make_table(strings, utf8)
    got, tail = read_table(arsc.rename_app(data, new, old_sha1=sha("Old Name")))
    assert got == ["Alpha", new, "Gamma", "Ñandú"] and tail == b"PACKAGE-CHUNK-BYTES"


def test_the_name_is_found_by_its_fingerprint_not_stored():
    """SPEC-013/R-10: the original name is identified by its SHA-1; a table that does not have it is refused."""
    assert len(arsc.ORIGINAL_NAME_SHA1) == 40 and int(arsc.ORIGINAL_NAME_SHA1, 16) >= 0
    with pytest.raises(arsc.ArscError, match="name of the app"):
        arsc.rename_app(make_table(["Alpha", "Beta"]), old_sha1=sha("Not there"))
    with pytest.raises(arsc.ArscError):
        arsc.rename_app(b"\x00" * 64)
