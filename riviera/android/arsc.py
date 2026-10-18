"""Rename the app in ``resources.arsc``.

The name the launcher shows is a string of the global pool of the compiled resources of ``base.apk``, in Japanese. Strings are referenced
by index, so replacing one is rewriting it, shifting the offsets of the ones after it and fixing the sizes of the chunks that contain it.
The old name is found by its SHA-1, so it is not stored here.
"""

from __future__ import annotations

import hashlib
import struct

from . import AndroidError

UTF8_FLAG = 0x100
APP_NAME = "Riviera"
#: SHA-1 of the app's name as the original resources spell it
ORIGINAL_NAME_SHA1 = "74621ade24d44638e0a78445f5691a56f32499f8"


class ArscError(AndroidError):
    """The resource table is not what this module understands."""


def _read_len(d, o, wide):
    if wide:
        n, = struct.unpack_from("<H", d, o)
        if n & 0x8000:
            return ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, o + 2)[0], o + 4
        return n, o + 2
    n = d[o]
    if n & 0x80:
        return ((n & 0x7F) << 8) | d[o + 1], o + 2
    return n, o + 1


def _enc_len(n, wide):
    if wide:
        return struct.pack("<H", n) if n < 0x8000 else struct.pack("<HH", 0x8000 | (n >> 16), n & 0xFFFF)
    return bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])


def _encode(s: str, utf8: bool) -> bytes:
    if utf8:
        b = s.encode("utf-8")
        return _enc_len(len(s.encode("utf-16-le")) // 2, False) + _enc_len(len(b), False) + b + b"\0"
    u = s.encode("utf-16-le")
    return _enc_len(len(u) // 2, True) + u + b"\0\0"


def _raw_string(d, o, utf8):
    """``(text, end)`` of the string encoded at ``d[o:]``."""
    if utf8:
        _, o = _read_len(d, o, False)
        n, o = _read_len(d, o, False)
        return d[o:o + n].decode("utf-8"), o + n + 1
    n, o = _read_len(d, o, True)
    return d[o:o + 2 * n].decode("utf-16-le"), o + 2 * n + 2


def rename_app(data: bytes, new: str = APP_NAME, old_sha1: str = ORIGINAL_NAME_SHA1) -> bytes:
    """``data`` (a ``resources.arsc``) with the string whose SHA-1 is ``old_sha1`` replaced by ``new``."""
    d = bytearray(data)
    t_type, t_hsize, _, _ = struct.unpack_from("<HHII", d, 0)
    if t_type != 0x0002:
        raise ArscError("not a resource table")
    p = t_hsize
    p_type, p_hsize, p_size, count, styles, flags, s_start, st_start = struct.unpack_from("<HHIIIIII", d, p)
    if p_type != 0x0001:
        raise ArscError("the global string pool is not where it should be")
    utf8 = bool(flags & UTF8_FLAG)
    offs = list(struct.unpack_from(f"<{count}I", d, p + p_hsize))
    base = p + s_start
    data_end = p + (st_start if styles else p_size)

    hits = [i for i, o in enumerate(offs) if hashlib.sha1(_raw_string(d, base + o, utf8)[0].encode("utf-8")).hexdigest() == old_sha1]
    if not hits:
        raise ArscError("the name of the app was not found in the resources (a different version of the app?)")
    target = offs[hits[0]]
    _, end = _raw_string(d, base + target, utf8)
    new_raw = _encode(new, utf8)
    delta = len(new_raw) - (end - (base + target))

    strings = bytes(d[base:data_end])
    strings = strings[:target] + new_raw + strings[end - base:]
    used = max(_raw_string(d, base + o, utf8)[1] - base for o in offs) + delta          # the string area is padded to a multiple of 4
    strings = strings[:used] + b"\0" * ((-used) % 4)
    new_offs = [o + delta if o > target else o for o in offs]

    header = bytearray(d[p:p + s_start])
    struct.pack_into(f"<{count}I", header, p_hsize, *new_offs)
    style_data = bytes(d[data_end:p + p_size]) if styles else b""
    new_st_start = s_start + len(strings) if styles else 0
    pool = header + strings + style_data
    struct.pack_into("<IIII", pool, 4, len(pool), count, styles, flags)
    struct.pack_into("<II", pool, 20, s_start, new_st_start)

    out = bytearray(d[:p]) + pool + d[p + p_size:]
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)
