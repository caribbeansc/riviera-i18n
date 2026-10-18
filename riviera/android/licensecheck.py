"""Switch off the Google Play licence check in your own copy of the Android app (optional, and off with ``--keep-license-check``).

**Why this exists.** The patched app has to be re-signed with a key of your own, because the original is signed by Google Play and
only the owner of that key can sign an update. The app carries Google's licence client (PairIP): at start-up it asks the Play
service whether the installed copy is licensed, and a re-signed copy is told no, the licence screen opens and the app closes. The
translation cannot work without getting past that check, so the builder disables it **in the copy you are patching**:
``com.pairip.licensecheck.LicenseClient.initializeLicenseCheck()`` is replaced by a ``return-void``. That is all it changes: nothing
of the app's own code, of Google Play or of anyone's account is touched, and nothing is downloaded.

**What it is for.** A copy of the game that *you bought*, patched on *your* machine for *your* phone. It is not a way to run a game you
did not pay for, and it is not offered as one.

**How.** The method's code item is rewritten in place (``return-void`` followed by ``nop`` for the rest of the instructions, so the
size of every structure of the file stays the same), and the two checks of the dex header, the Adler-32 checksum and the SHA-1
signature, are recomputed. No apktool, no Java.

Where the licence client lives can change when the app is updated; a dex without it raises :class:`LicenseCheckNotFound`.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

from . import AndroidError

LICENSE_CLASS = "Lcom/pairip/licensecheck/LicenseClient;"
LICENSE_METHOD = "initializeLicenseCheck"

RETURN_VOID = 0x000E            # the Dalvik opcode `return-void`; every unit after it is a `nop` (0x0000)


class LicenseCheckError(AndroidError):
    """The dex is not one this module can read."""


class LicenseCheckNotFound(LicenseCheckError):
    """The dex does not contain the licence client."""


def _uleb(d: bytes, o: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        b = d[o]
        o += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, o
        shift += 7


def _string(d: bytes, string_ids_off: int, idx: int) -> bytes:
    off, = struct.unpack_from("<I", d, string_ids_off + 4 * idx)
    _, o = _uleb(d, off)                       # the length in UTF-16 units; the bytes end at a NUL
    return d[o:d.index(b"\0", o)]


def find_code_item(dex: bytes) -> int | None:
    """Offset of the code item of ``LicenseClient.initializeLicenseCheck()V``, or ``None`` if the dex has no such method."""
    if dex[:4] != b"dex\n":
        raise LicenseCheckError("not a dex file")
    (s_size, s_off, t_size, t_off, p_size, p_off, _f_size, _f_off, m_size, m_off, c_size, c_off) = struct.unpack_from("<12I", dex, 0x38)
    try:
        wanted = next(i for i in range(t_size)
                      if _string(dex, s_off, struct.unpack_from("<I", dex, t_off + 4 * i)[0]) == LICENSE_CLASS.encode())
    except StopIteration:
        return None
    for ci in range(c_size):
        class_idx, _, _, _, _, _, class_data_off, _ = struct.unpack_from("<8I", dex, c_off + 32 * ci)
        if class_idx != wanted or not class_data_off:
            continue
        o = class_data_off
        n_static, o = _uleb(dex, o)
        n_inst, o = _uleb(dex, o)
        n_direct, o = _uleb(dex, o)
        n_virtual, o = _uleb(dex, o)
        for _ in range(n_static + n_inst):                       # (field_idx_diff, access_flags)
            _, o = _uleb(dex, o)
            _, o = _uleb(dex, o)
        for count in (n_direct, n_virtual):
            idx = 0
            for _ in range(count):
                diff, o = _uleb(dex, o)
                _, o = _uleb(dex, o)
                code_off, o = _uleb(dex, o)
                idx += diff
                mclass, mproto, mname = struct.unpack_from("<HHI", dex, m_off + 8 * idx)
                if mclass != wanted or _string(dex, s_off, mname) != LICENSE_METHOD.encode():
                    continue
                _, ret_type, params = struct.unpack_from("<3I", dex, p_off + 12 * mproto)
                ret = _string(dex, s_off, struct.unpack_from("<I", dex, t_off + 4 * ret_type)[0])
                if ret == b"V" and params == 0 and code_off:
                    return code_off
    return None


def is_patched(dex: bytes) -> bool:
    code = find_code_item(dex)
    if code is None:
        return False
    size, = struct.unpack_from("<I", dex, code + 12)
    units = struct.unpack_from(f"<{size}H", dex, code + 16)
    return size >= 1 and units[0] == RETURN_VOID and not any(units[1:])


def fix_header(buf: bytearray) -> None:
    """Recompute the SHA-1 signature (bytes 0x20 to the end) and then the Adler-32 checksum (bytes 0x0C to the end)."""
    buf[12:32] = hashlib.sha1(bytes(buf[32:])).digest()
    struct.pack_into("<I", buf, 8, zlib.adler32(bytes(buf[12:])) & 0xFFFFFFFF)


def patch_dex(dex: bytes) -> bytes:
    """``dex`` with the licence check disabled. Returns it unchanged if it already is; raises :class:`LicenseCheckNotFound` if the
    dex has no licence client."""
    code = find_code_item(dex)
    if code is None:
        raise LicenseCheckNotFound("this dex does not contain the licence client")
    if is_patched(dex):
        return dex
    size, = struct.unpack_from("<I", dex, code + 12)
    if size < 1:
        raise LicenseCheckError("the licence method has no instructions to replace")
    buf = bytearray(dex)
    struct.pack_into(f"<{size}H", buf, code + 16, RETURN_VOID, *([0] * (size - 1)))
    fix_header(buf)
    return bytes(buf)


def verify_header(dex: bytes) -> bool:
    """Do the checksum and the signature in the header match the contents?"""
    return (hashlib.sha1(dex[32:]).digest() == dex[12:32]
            and struct.unpack_from("<I", dex, 8)[0] == zlib.adler32(dex[12:]) & 0xFFFFFFFF)
