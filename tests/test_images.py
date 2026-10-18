"""SPEC-003: translated artwork without the game's artwork."""

import io

import pytest
from PIL import Image

import synth
from riviera import images, pck


def _im(color, size=(10, 6)):
    return Image.new("RGBA", size, color)


def test_delta_roundtrip():
    """SPEC-003/R-1, R-3"""
    a = _im((10, 20, 30, 255))
    b = a.copy()
    b.paste((200, 100, 50, 255), (2, 1, 5, 4))
    overlay, mask, fraction = images.make_delta(a, b)
    assert 0 < fraction < 1
    assert images.apply_delta(a, overlay, mask).tobytes() == b.tobytes()
    assert overlay.getpixel((0, 0)) == (0, 0, 0, 0)                       # outside the mask the overlay is empty


def test_unchanged_picture_has_an_empty_mask():
    """SPEC-003/R-4"""
    a = _im((1, 2, 3, 255))
    _, mask, fraction = images.make_delta(a, a.copy())
    assert fraction == 0 and mask.getbbox() is None


def test_a_pixel_can_change_to_transparent():
    """SPEC-003/R-2: erasing text on an alpha background must be recorded."""
    a = _im((255, 255, 255, 255))
    b = a.copy()
    b.putpixel((3, 3), (0, 0, 0, 0))
    overlay, mask, _ = images.make_delta(a, b)
    assert mask.getpixel((3, 3)) == 255
    assert images.apply_delta(a, overlay, mask).getpixel((3, 3)) == (0, 0, 0, 0)


def test_two_transparent_pixels_are_equal_whatever_their_colour():
    """SPEC-003/R-2: otherwise the delta of a picture with an alpha background would be the whole picture."""
    a = _im((255, 0, 0, 0))
    b = _im((0, 255, 0, 0))
    _, mask, fraction = images.make_delta(a, b)
    assert fraction == 0 and mask.getbbox() is None


def test_delta_needs_the_same_size():
    """SPEC-003/R-1"""
    with pytest.raises(images.ImageError):
        images.make_delta(_im((0, 0, 0, 255)), _im((0, 0, 0, 255), (4, 4)))


def test_a_delta_made_at_another_size_is_scaled_not_cropped():
    """SPEC-003/R-7"""
    a = _im((9, 9, 9, 255), (20, 12))
    overlay, mask = _im((1, 1, 1, 255), (10, 6)), Image.new("L", (10, 6), 255)
    assert images.apply_delta(a, overlay, mask).getpixel((19, 11)) == (1, 1, 1, 255)


def test_package_is_rebuilt_from_full_and_delta_entries(langs):
    """SPEC-003/R-5, R-6"""
    original = synth.make_pck({"story_00.webp": synth.webp((16, 8), (10, 20, 30, 255)),
                               "panel.webp": synth.webp((16, 8), (200, 200, 200, 255)),
                               "keep.webp": synth.webp((4, 4))})
    entries = images.packages(images.load_manifest(langs.pack.path), "data_en.bin")["data/event/demo.pck"]
    new, warnings = images.build_package(langs.pack.path, entries, original)
    assert warnings == []
    ents = dict((pck.entry_name(n), b) for n, b in pck.read_pck(new)[1])
    assert Image.open(io.BytesIO(ents["story_00.webp"])).size == (40, 12)              # a full picture: new size
    panel = images.decode(ents["panel.webp"])
    assert panel.getpixel((3, 3)) == (0, 0, 0, 255) and panel.getpixel((12, 6)) == (200, 200, 200, 255)
    assert ents["keep.webp"] == dict((pck.entry_name(n), b) for n, b in pck.read_pck(original)[1])["keep.webp"]


def test_a_different_original_is_reported(langs):
    """SPEC-003/R-9"""
    other = synth.make_pck({"story_00.webp": synth.webp((16, 8), (99, 99, 99, 255)),
                            "panel.webp": synth.webp((16, 8), (200, 200, 200, 255))})
    entries = images.packages(images.load_manifest(langs.pack.path), "data_en.bin")["data/event/demo.pck"]
    _, warnings = images.build_package(langs.pack.path, entries, other, label="demo")
    assert len(warnings) == 1 and "story_00.webp" in warnings[0]


def test_a_missing_entry_is_an_error(langs):
    """SPEC-003/R-9"""
    entries = images.packages(images.load_manifest(langs.pack.path), "data_en.bin")["data/event/demo.pck"]
    with pytest.raises(images.ImageError):
        images.build_package(langs.pack.path, entries, synth.make_pck({"other.webp": synth.webp()}))


def test_translated_packages_reads_the_users_container(dump, langs):
    """SPEC-003/R-10"""
    out, warnings = images.translated_packages(langs.pack.path, dump.romfs / "data_en.bin")
    assert list(out) == ["data/event/demo.pck"] and warnings == []


def test_a_rectangular_mask_does_not_trace_the_text_it_replaces():
    """SPEC-003/R-11"""
    a = _im((0, 0, 0, 0), (24, 10))
    for x in range(2, 8):
        a.putpixel((x, 3), (255, 255, 255, 255))                  # the old label: an L-shaped glyph
    for y in range(3, 8):
        a.putpixel((2, y), (255, 255, 255, 255))
    b = _im((0, 0, 0, 0), (24, 10))
    for x in range(12, 20):
        b.putpixel((x, 5), (255, 255, 255, 255))                  # the new label somewhere else
    exact = images.make_delta(a, b)[1]
    overlay, mask, fraction = images.make_delta(a, b, rect=True)
    box = exact.getbbox()
    assert mask.getbbox() == box
    assert all(mask.getpixel((x, y)) == 255 for x in range(box[0], box[2]) for y in range(box[1], box[3]))
    assert any(exact.getpixel((x, y)) == 0 for x in range(box[0], box[2]) for y in range(box[1], box[3]))   # the exact one had holes
    assert images.apply_delta(a, overlay, mask).tobytes() == b.tobytes()
    assert fraction > images.make_delta(a, b)[2]
