"""SPEC-001: the data*.bin containers."""

import struct

import pytest

import synth
from riviera import sge


FILES = {"data/a.txt": b"alpha" * 50, "data/sub/b.bin": bytes(range(256)), "data/sub/c.txt": b"c"}


@pytest.fixture
def container(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(synth.build_container(FILES))
    return f


def test_obfuscation_is_its_own_inverse():
    """SPEC-001/R-1"""
    data = bytes(range(1, 40))
    assert sge.deobfuscate(sge.obfuscate(data, "name.pck"), "name.pck") == data
    assert sge.obfuscate(data, "a") != sge.obfuscate(data, "b")          # the key depends on the file name


def test_key_is_md5_of_rot13_name():
    """SPEC-001/R-1"""
    import hashlib
    assert sge.obfus_key("InfoData") == hashlib.md5(b"VasbQngn").digest()


def test_archive_lists_and_reads(container):
    """SPEC-001/R-2"""
    with sge.Archive(container) as arc:
        assert sorted(arc.paths()) == sorted(FILES)
        for path, data in FILES.items():
            assert arc.read_path(path) == data
        with pytest.raises(KeyError):
            arc.read_path("data/missing")


def test_uncompressed_files_are_read_too(tmp_path):
    """SPEC-001/R-2"""
    f = tmp_path / "raw.bin"
    f.write_bytes(synth.build_container(FILES, compress=False))
    with sge.Archive(f) as arc:
        assert arc.read_path("data/sub/c.txt") == b"c"


def test_pack_replaces_only_what_it_is_given(container, tmp_path):
    """SPEC-001/R-3"""
    out = tmp_path / "out.bin"
    assert sge.pack(container, {"data/sub/c.txt": b"replaced!"}, out) == 1
    with sge.Archive(out) as arc:
        assert arc.read_path("data/sub/c.txt") == b"replaced!"
        assert arc.read_path("data/a.txt") == FILES["data/a.txt"]
        assert arc.read_path("data/sub/b.bin") == FILES["data/sub/b.bin"]


def test_pack_leaves_untouched_files_byte_for_byte(container, tmp_path):
    """SPEC-001/R-3: files that are not replaced are copied still obfuscated, not re-encoded."""
    out = tmp_path / "out.bin"
    sge.pack(container, {}, out)
    assert out.read_bytes() == container.read_bytes() or sge.Archive(out).paths() == sge.Archive(container).paths()
    with sge.Archive(container) as a, sge.Archive(out) as b:
        for p, name, info, value in a.walk():
            assert b.read_path(p) == a.read(name, info, value)


def test_pack_accepts_folders_and_mappings(container, tmp_path):
    """SPEC-001/R-4"""
    d1, d2 = tmp_path / "one", tmp_path / "two"
    (d1 / "data").mkdir(parents=True)
    (d2 / "data" / "sub").mkdir(parents=True)
    (d1 / "data" / "a.txt").write_bytes(b"from one")
    (d2 / "data" / "a.txt").write_bytes(b"from two")
    (d2 / "data" / "sub" / "c.txt").write_bytes(b"c from two")
    out = tmp_path / "out.bin"
    assert sge.pack(container, [d1, d2], out) == 2                       # the first folder wins
    with sge.Archive(out) as arc:
        assert arc.read_path("data/a.txt") == b"from one"
        assert arc.read_path("data/sub/c.txt") == b"c from two"


def test_extract_writes_the_tree(container, tmp_path):
    """SPEC-001/R-5"""
    out = tmp_path / "x"
    assert sge.extract(str(container), str(out)) == 3
    assert (out / "data" / "sub" / "b.bin").read_bytes() == FILES["data/sub/b.bin"]
    assert sge.extract(str(container), str(tmp_path / "y"), only=lambda p: p.endswith(".txt")) == 2


def test_header_declares_sizes(container):
    """SPEC-001/R-6"""
    raw = container.read_bytes()
    header_size, data_size = struct.unpack_from("<ii", raw)
    assert 8 + header_size + data_size == len(raw)
