"""SPEC-012: switching off the Google Play licence check in your own copy of the app (optional step of the Android build)."""

import struct

import pytest

from riviera.android import licensecheck as L


def uleb(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def build_dex(with_client: bool = True, insns=(0x1234, 0x5678, 0x9ABC, 0x0D0E, 0x000E)) -> bytes:
    """A minimal but well-formed dex: one class with one static method ``()V``, enough for the parts the patcher reads."""
    cls = L.LICENSE_CLASS if with_client else "Lcom/example/Other;"
    strings = ["V", cls, L.LICENSE_METHOD]                      # 0: shorty and return type, 1: class, 2: method name
    # layout: header 0x70, string_ids, type_ids, proto_ids, method_ids, class_defs, then the data
    n_s, n_t, n_p, n_m, n_c = len(strings), 2, 1, 1, 1
    off_s = 0x70
    off_t = off_s + 4 * n_s
    off_p = off_t + 4 * n_t
    off_m = off_p + 12 * n_p
    off_c = off_m + 8 * n_m
    data = off_c + 32 * n_c
    blobs, offs = bytearray(), []
    for s in strings:                                           # string_data_item: uleb128 length, MUTF-8, NUL
        offs.append(data + len(blobs))
        blobs += uleb(len(s)) + s.encode() + b"\0"
    while (data + len(blobs)) % 4:
        blobs += b"\0"
    code_off = data + len(blobs)
    code = struct.pack("<4HII", 2, 0, 1, 0, 0, len(insns)) + struct.pack(f"<{len(insns)}H", *insns)
    blobs += code
    while (data + len(blobs)) % 4:
        blobs += b"\0"
    class_data_off = data + len(blobs)
    blobs += uleb(0) + uleb(0) + uleb(1) + uleb(0)             # no fields, one direct method
    blobs += uleb(0) + uleb(0x9) + uleb(code_off)               # method_idx_diff, public static, code
    body = bytearray()
    body += b"".join(struct.pack("<I", o) for o in offs)
    body += struct.pack("<II", 1, 0)                            # type 0 = the class (string 1), type 1 = "V" (string 0)
    body += struct.pack("<III", 0, 1, 0)                        # proto: shorty "V", returns type 1, no parameters
    body += struct.pack("<HHI", 0, 0, 2)                        # method: class 0, proto 0, name string 2
    body += struct.pack("<8I", 0, 1, 0xFFFFFFFF, 0, 0xFFFFFFFF, 0, class_data_off, 0)
    body += blobs
    size = 0x70 + len(body)
    head = bytearray(0x70)
    head[:8] = b"dex\n035\0"
    struct.pack_into("<I", head, 0x20, size)
    struct.pack_into("<I", head, 0x24, 0x70)
    struct.pack_into("<I", head, 0x28, 0x12345678)
    struct.pack_into("<12I", head, 0x38, n_s, off_s, n_t, off_t, n_p, off_p, 0, 0, n_m, off_m, n_c, off_c)
    struct.pack_into("<II", head, 0x68, len(body) - 4 * n_s - 8 * n_t - 12 * n_p - 8 * n_m - 32 * n_c, data)
    dex = bytearray(head + body)
    L.fix_header(dex)
    return bytes(dex)


def test_the_method_is_found_by_class_name_and_prototype():
    """SPEC-012/R-1"""
    dex = build_dex()
    code = L.find_code_item(dex)
    assert code is not None and struct.unpack_from("<I", dex, code + 12)[0] == 5
    assert L.find_code_item(build_dex(with_client=False)) is None


def test_the_instructions_become_return_void_and_nops_in_place():
    """SPEC-012/R-2: nothing else in the file changes, so every size and offset of the dex stays valid."""
    dex = build_dex()
    patched = L.patch_dex(dex)
    code = L.find_code_item(patched)
    assert struct.unpack_from("<5H", patched, code + 16) == (0x000E, 0, 0, 0, 0)
    assert len(patched) == len(dex)
    changed = [i for i in range(len(dex)) if dex[i] != patched[i]]
    assert all(i < 32 or code + 16 <= i < code + 26 for i in changed)         # the header's checksum + signature, and the five units
    assert L.is_patched(patched) and not L.is_patched(dex)


def test_the_header_is_valid_after_patching():
    """SPEC-012/R-3"""
    dex = build_dex()
    assert L.verify_header(dex)
    patched = L.patch_dex(dex)
    assert L.verify_header(patched)
    assert patched[8:32] != dex[8:32]                                          # the checksum and the signature were recomputed


def test_patching_twice_changes_nothing():
    """SPEC-012/R-4"""
    once = L.patch_dex(build_dex())
    assert L.patch_dex(once) == once


def test_a_dex_without_the_client_and_a_non_dex_are_refused():
    """SPEC-012/R-5"""
    with pytest.raises(L.LicenseCheckNotFound):
        L.patch_dex(build_dex(with_client=False))
    with pytest.raises(L.LicenseCheckError):
        L.patch_dex(b"PK\x03\x04 not a dex")


@pytest.mark.game
def test_the_real_app_has_the_client_in_its_first_dex():
    """SPEC-012/R-1: against the base.apk of your own app (python rpl.py setup --apk-dir ...)."""
    import zipfile
    from riviera import config
    proj = config.load()
    if not proj.has_android():
        pytest.skip("no Android app configured")
    with zipfile.ZipFile(proj.apk_dir / "base.apk") as z:
        found = [n for n in z.namelist() if n.startswith("classes") and n.endswith(".dex") and L.find_code_item(z.read(n))]
        assert found, "no dex of base.apk has the licence client"
        patched = L.patch_dex(z.read(found[0]))
    assert L.verify_header(patched) and L.is_patched(patched)
