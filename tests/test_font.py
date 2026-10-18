"""SPEC-010: the accented letters in the game's font."""

import io

from PIL import Image

import synth
from riviera import font, ips, pck
from riviera import nso as N


def _nso(dump):
    return N.Nso(dump.exefs / "main")


def test_every_spanish_character_has_a_cell(dump):
    """SPEC-010/R-1"""
    s = font.charset(_nso(dump), dump.build)
    cells = font.cells_for(s)
    assert set(cells) == set(font.NATIVE) | set(font.REPLACE)
    assert cells["¿"] == s.index("Þ") and cells["¡"] == s.index("Ð")      # taken over from characters the game never uses


def test_atlas_grows_to_43_rows_and_gets_glyphs(dump):
    """SPEC-010/R-2"""
    n = _nso(dump)
    from riviera.sge import Archive
    with Archive(dump.romfs / "data.bin") as arc:
        original = arc.read_path(font.ATLAS_PCK)
    atlas = font.make_atlas(n, original, dump.build)
    _, ents = pck.read_pck(atlas.pck)
    names = pck.names(ents)
    assert names == list(font.ATLASES) + ["other.webp"]                          # the other pictures of the package are untouched
    for name in font.ATLASES:
        im = Image.open(io.BytesIO(ents[names.index(name)][1]))
        assert im.size == (font.COLS * font.CELL, font.ROWS * font.CELL)
    glyph_cell = font.cell(Image.open(io.BytesIO(ents[0][1])).convert("RGBA"), atlas.cells["ñ"])
    assert glyph_cell.getchannel("A").getbbox() is not None                # something was drawn in the cell of ñ
    assert set(atlas.glyphs) == set(font.BASE) | set(font.FLIP)


def test_other_pictures_are_not_reencoded(dump):
    """SPEC-010/R-2"""
    from riviera.sge import Archive
    with Archive(dump.romfs / "data.bin") as arc:
        original = arc.read_path(font.ATLAS_PCK)
    atlas = font.make_atlas(_nso(dump), original, dump.build)
    assert pck.read_pck(atlas.pck)[1][2][1] == pck.read_pck(original)[1][2][1]


def test_exe_patch_swaps_the_two_characters_and_adds_metrics(dump):
    """SPEC-010/R-3"""
    n = _nso(dump)
    from riviera.sge import Archive
    with Archive(dump.romfs / "data.bin") as arc:
        atlas = font.make_atlas(n, arc.read_path(font.ATLAS_PCK), dump.build)
    patched = N.Nso.from_image(ips.apply_ips(ips.to_ips(atlas.writes, n.image), n.image), dump.build.build_id)
    s = font.charset(patched, dump.build)
    assert "¿" in s and "¡" in s and "Þ" not in s and "Ð" not in s
    assert len(s) == len(font.charset(n, dump.build))                      # the string keeps its length: cells do not move


def test_metrics_know_the_new_glyphs(dump):
    """SPEC-010/R-4: line widths must count the new letters with their real width."""
    n = _nso(dump)
    from riviera.sge import Archive
    with Archive(dump.romfs / "data.bin") as arc:
        atlas = font.make_atlas(n, arc.read_path(font.ATLAS_PCK), dump.build)
    M, _ = font.font_metrics(n, atlas.writes, dump.build)
    assert M.glyph("ñ") != 68 and M.glyph("é") != 68
    assert M.glyph("a") > 0


def test_missing_glyphs_are_reported():
    """SPEC-010/R-5"""
    charset = synth.charset_string()
    assert font.missing_glyphs({"a": 3, "é": 2, "¿": 1, "[": 1}, charset) == {}
    assert font.missing_glyphs({"€": 4}, charset) == {"€": 4}
