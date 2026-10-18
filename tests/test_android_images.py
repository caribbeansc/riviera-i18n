"""Tests of riviera.android.images, assets and sprites on synthetic containers (SPEC-016). No game files are needed."""

import io
import json
import zipfile

import pytest
from PIL import Image

import synth
from riviera import images as swimages
from riviera import pck
from riviera.android import images, sprites
from riviera.android.assets import CONTAINERS, AndroidAssets, AssetError
from riviera.packs import LangPack

RED, GREEN, BLUE = (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)


def wp(size, color):
    return synth.webp(size, color)


def make_assets(tmp_path, containers):
    """The user's expansion APK with the four containers (``containers``: ``{"data.bin": {path: bytes}}``)."""
    apk_dir = tmp_path / "apks"
    apk_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(apk_dir / "split_asset_expansion.apk", "w") as z:
        for name in CONTAINERS:
            z.writestr(f"assets/{name}", synth.build_container(containers.get(name) or {"data/_.txt": b"-"}))
    return AndroidAssets(apk_dir, tmp_path / "work")


def make_donor(tmp_path, english, common=None, translated=None):
    romfs = tmp_path / "romfs"
    romfs.mkdir(exist_ok=True)
    (romfs / "data_en.bin").write_bytes(synth.build_container(english))
    (romfs / "data.bin").write_bytes(synth.build_container(common or {"data/_.txt": b"-"}))
    return images.Donor(romfs, translated)


def make_pack(tmp_path, manifest=None, files=None):
    folder = tmp_path / "pack"
    (folder / "android" / "images").mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (folder / "android" / "images" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, data in (files or {}).items():
        (folder / "android" / "images" / name).write_bytes(data)
    return LangPack(code="xx", path=folder, meta={"code": "xx", "mod_name": "X"})


def decode(blob):
    return Image.open(io.BytesIO(blob)).convert("RGBA")


# --------------------------------------------------------- rules and sizes --

def test_classify_follows_the_first_matching_pattern():
    """SPEC-016/R-3: omit, generate, fit, copy and height, by path pattern, the first match wins."""
    assert images.classify("data/System/systemTexture.pck::skl_win_base.webp") == "omit"
    assert images.classify("data/System/systemTexture.pck::tap_to_quest.webp") == "omit"
    assert images.classify("data/Backup/backup.pck::backup_clear.webp") == "generate"
    assert images.classify("data/skillname/eskillName00.webp::*") == "generate"
    assert images.classify("data/System/config.pck::dot_filter_chara_on.webp") == "fit"
    assert images.classify("data/System/systemTexture.pck::largename3.webp") == "copy"
    assert images.classify("data/System/config.pck::config_battle_headtxt.webp") == "height"


def test_height_keeps_the_proportion_of_the_letter_and_squeezes_option_labels():
    """SPEC-016/R-4: scaled to the height of the Android picture keeping the width; the labels of the options screen fit their column."""
    switch = Image.new("RGBA", (100, 20), RED)
    android = Image.new("RGBA", (80, 10), GREEN)
    assert images.derive("height", switch, android, "data/x.pck", "a.webp").size == (50, 10)
    assert images.derive("copy", switch, android, "data/x.pck", "a.webp").size == (100, 20)
    assert images.derive("fit", switch, android, "data/x.pck", "a.webp").size == (80, 10)
    wide, tall = Image.new("RGBA", (2000, 40), RED), Image.new("RGBA", (400, 20), GREEN)
    assert images.derive("height", wide, tall, "data/System/config.pck", "txt_label.webp").size == (images.CONFIG_LABEL_CAP, 20)
    assert images.derive("height", wide, tall, "data/System/config.pck", "txt_label2.webp").size == (images.CONFIG_TEXT_CAP, 20)
    assert images.derive("height", wide, tall, "data/System/systemTexture.pck", "txt_label.webp").size == (1000, 20)


def test_by_name_replacement_rules():
    """SPEC-016/R-2: same size is taken, another size too unless the Android picture is a big one; the generated picture wins."""
    android = synth.make_pck({
        "..\\a\\same.webp": wp((8, 8), RED), "..\\a\\other.webp": wp((8, 8), RED), "..\\a\\sheet.webp": wp((300, 200), RED),
        "..\\a\\gen.webp": wp((8, 8), RED), "..\\a\\equal.webp": wp((8, 8), RED), "..\\a\\only_android.webp": wp((8, 8), RED)})
    switch = synth.make_pck({"x\\same.webp": wp((8, 8), GREEN), "x\\other.webp": wp((16, 16), GREEN), "x\\sheet.webp": wp((100, 100), GREEN),
                             "x\\gen.webp": wp((8, 8), GREEN), "x\\equal.webp": wp((8, 8), RED)})
    blob, stat = images.merge_package(android, switch, {"gen.webp": b"GENERATED"}, "t")
    got = {images.base_name(pck.entry_name(e[0])): e[1] for e in pck.read_pck(blob)[1]}
    assert decode(got["same.webp"]).getpixel((0, 0)) == GREEN and decode(got["same.webp"]).size == (8, 8)
    assert decode(got["other.webp"]).size == (16, 16)                                    # taken at its own size
    assert decode(got["sheet.webp"]).size == (300, 200)                                  # a big picture may be a sprite sheet: kept
    assert got["gen.webp"] == b"GENERATED"
    assert decode(got["equal.webp"]).getpixel((0, 0)) == RED and decode(got["only_android.webp"]).getpixel((0, 0)) == RED
    assert stat["generated"] == 1 and stat["switch"] == 1 and stat["switch_other_size"] == 1 and "sheet.webp (300, 200)->(100, 100)" in stat["skipped"]


def test_inventory_compares_android_pictures_with_switch(tmp_path):
    """SPEC-016/R-3: identical, same size, another size or no counterpart, per picture of the listed files."""
    assets = make_assets(tmp_path, {"data.bin": {"data/System/config.pck": synth.make_pck({
        "a\\same.webp": wp((8, 8), RED), "a\\samesize.webp": wp((8, 8), RED), "a\\othersize.webp": wp((8, 8), RED), "a\\alone.webp": wp((8, 8), RED)})}})
    donor = make_donor(tmp_path, {"data/System/config.pck": synth.make_pck({
        "b\\same.webp": wp((8, 8), RED), "b\\samesize.webp": wp((8, 8), GREEN), "b\\othersize.webp": wp((12, 8), RED)})})
    rows = {entry.split("\\")[-1]: kind for f, entry, kind in images.inventory(assets, donor) if f == "data/System/config.pck"}
    assert rows == {"same.webp": "same", "samesize.webp": "same_size", "othersize.webp": "other_size", "alone.webp": "no_counterpart"}
    donor.close()
    assets.close()


# ----------------------------------------------------------- pack pictures --

def test_the_pack_pictures_full_delta_and_layer(tmp_path):
    """SPEC-016/R-5, SPEC-016/R-6: full replaces, delta edits the user's original, layer composes our text with a piece of the original."""
    original, panel = wp((20, 10), RED), wp((20, 10), (200, 200, 200, 255))
    assets = make_assets(tmp_path, {"data.bin": {"data/Backup/backup.pck": synth.make_pck({"..\\b\\one.webp": original, "..\\b\\two.webp": panel,
                                                                                          "..\\b\\three.webp": original})}})
    edited = swimages.decode(panel).copy()
    edited.paste((0, 0, 0, 255), (2, 2, 6, 6))
    overlay, mask, _ = swimages.make_delta(swimages.decode(panel), edited)
    blue = Image.new("RGBA", (10, 10), BLUE)
    files = {"one.webp": wp((40, 12), GREEN)}
    for name, im in (("two.png", overlay), ("two.mask.png", mask), ("three.png", blue)):
        buf = io.BytesIO()
        im.save(buf, "PNG")
        files[name] = buf.getvalue()
    manifest = {"format": 1, "containers": {"android": {"data/Backup/backup.pck": {
        "one.webp": {"kind": "full", "file": "one.webp", "base": swimages.sha1(original)},
        "two.webp": {"kind": "delta", "overlay": "two.png", "mask": "two.mask.png", "base": swimages.sha1(panel)},
        "three.webp": {"kind": "layer", "size": [20, 10], "bleed": [1, 2, 3], "base": "0" * 40,
                       "ops": [{"op": "copy", "from": None, "box": [0, 0, 5, 10], "to": [0, 0]}, {"op": "layer", "file": "three.png", "at": [10, 0]}]}}}}}
    pack = make_pack(tmp_path, manifest, files)
    got, warnings = images.pack_images(pack, assets)
    out = got["data/Backup/backup.pck"]
    assert decode(out["one.webp"]).size == (40, 12)                                      # a full picture may have another size
    two = decode(out["two.webp"])
    assert two.getpixel((3, 3)) == (0, 0, 0, 255) and two.getpixel((15, 8)) == (200, 200, 200, 255)
    three = decode(out["three.webp"])
    assert three.getpixel((2, 5)) == RED and three.getpixel((12, 5)) == BLUE             # a piece of the original, then our layer
    assert three.getpixel((7, 5)) == (1, 2, 3, 0)                                         # the colour of the transparent pixels is kept
    assert warnings == ["data/Backup/backup.pck/three.webp: not the picture this translation was made against"]
    manifest["containers"]["android"]["data/Backup/backup.pck"]["missing.webp"] = {"kind": "full", "file": "one.webp"}
    (tmp_path / "pack" / "android" / "images" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(images.AndroidImageError, match="missing.webp"):
        images.pack_images(pack, assets)
    assets.close()


def test_a_loose_file_is_its_own_package(tmp_path):
    """SPEC-016/R-5: a loose picture (not in a package) is listed with the entry ``*``."""
    assets = make_assets(tmp_path, {"data.bin": {"data/skillname/x.webp": wp((8, 8), RED)}})
    pack = make_pack(tmp_path, {"format": 1, "containers": {"android": {"data/skillname/x.webp": {"*": {"kind": "full", "file": "x.webp"}}}}},
                     {"x.webp": wp((16, 4), GREEN)})
    got, _ = images.pack_images(pack, assets)
    assert decode(got["data/skillname/x.webp"]["*"]).size == (16, 4)
    assets.close()


def arrow(text_box=(20, 15, 29, 19)):
    """A button: transparent surround, white outline, flat body and a white label printed on the body."""
    from PIL import ImageDraw
    im = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([4, 4, 55, 35], fill=(255, 255, 255, 255))
    d.rectangle([6, 6, 53, 33], fill=(200, 120, 70, 255))
    d.rectangle(list(text_box), fill=(255, 255, 255, 255))
    return im


def test_erase_enclosed_paints_the_label_with_the_colour_of_the_button():
    """SPEC-016/R-6: what is printed on the flat body is painted over with the body colour; the outline stays; the box of the text is returned."""
    erased, box = images.erase_enclosed(arrow())
    assert box == (20, 15, 29, 19)
    assert erased.getpixel((25, 17)) == (200, 120, 70, 255) and erased.getpixel((20, 15)) == (200, 120, 70, 255)
    assert erased.getpixel((5, 5)) == (255, 255, 255, 255) and erased.getpixel((0, 0)) == (0, 0, 0, 0)       # outline and surround untouched
    assert erased.getpixel((40, 25)) == (200, 120, 70, 255)
    with pytest.raises(images.AndroidImageError):
        images.erase_enclosed(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))                                      # nothing to erase from
    with pytest.raises(images.AndroidImageError):
        images.erase_enclosed(Image.new("RGBA", (10, 10), (200, 120, 70, 255)))                               # a body but no text


def test_a_layer_can_erase_the_label_and_be_saved_plain(tmp_path):
    """SPEC-016/R-6, SPEC-016/R-12: copy the user's picture, erase its label, write ours; ``encode: plain`` saves it like any other picture."""
    original = io.BytesIO()
    arrow().save(original, "WEBP", lossless=True)
    text = Image.new("RGBA", (8, 4), BLUE)
    folder = tmp_path / "pack" / "android" / "images"
    folder.mkdir(parents=True)
    text.save(folder / "t.png")
    spec = {"kind": "layer", "size": [60, 40], "encode": "plain",
            "ops": [{"op": "copy", "from": None, "box": [0, 0, 60, 40], "to": [0, 0]}, {"op": "erase_enclosed"},
                    {"op": "layer", "file": "t.png", "at": [21, 16]}]}
    out = images.compose_layers(spec, tmp_path / "pack" / "android", {}, original.getvalue())
    made = decode(out)
    assert made.getpixel((22, 17)) == BLUE                                     # our text
    assert made.getpixel((29, 19)) == (200, 120, 70, 255)                      # the rest of the old label is gone
    assert made.getpixel((5, 5)) == (255, 255, 255, 255)                       # the outline is the user's own
    assert out == swimages.encode_webp(made.copy()) or decode(out).tobytes() == made.tobytes()


def test_a_layer_may_fall_partly_outside_the_canvas():
    """SPEC-016/R-6: a text layer wider than the canvas is clipped, not an error."""
    canvas = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    images.paste_over(canvas, Image.new("RGBA", (20, 4), RED), (-5, 3))
    assert canvas.getpixel((0, 3)) == RED and canvas.getpixel((9, 6)) == RED and canvas.getpixel((0, 7)) == (0, 0, 0, 0)


# -------------------------------------------------------------- code-made --

def letters_picture():
    """Four white rectangles on a transparent canvas, standing for the letters of LOOK."""
    im = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
    for k in range(4):
        im.paste((255, 255, 255, 255), (10 + 45 * k, 10, 45 + 45 * k, 50))
    return im


def sprite_original(size, fill):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    im.paste((0, 0, 0, 255), (0, 0, 40, 40))
    im.paste((240, 120, 50, 255), (0, 40, 40, 80))
    im.paste(fill + (255,), (40, 0, 80, 40))
    return im


def test_look_sprites_are_drawn_from_four_letters():
    """SPEC-016/R-7: the LOOK sprites take their canvas and colours from the user's QUEST ones and need exactly four letters."""
    big, small = sprites.look_sprites(letters_picture(), sprite_original((443, 166), (255, 255, 255)), sprite_original((464, 105), (228, 228, 228)))
    assert big.size == (443, 166) and small.size == (464, 105)
    data = big.tobytes()
    pixels = [data[i:i + 4] for i in range(0, len(data), 4)]
    assert any(px[3] > 200 and px[0] > 200 and px[2] < 120 for px in pixels)             # the orange ring
    assert any(px[3] > 200 and max(px[:3]) < 80 for px in pixels)                        # the black line
    with pytest.raises(ValueError, match="4 letters"):
        sprites.look_sprites(Image.new("RGBA", (50, 50), (0, 0, 0, 0)), sprite_original((443, 166), (255, 255, 255)),
                             sprite_original((464, 105), (228, 228, 228)))


def test_minigame_labels_are_fitted_into_the_android_canvas(tmp_path):
    """SPEC-016/R-8: bigger labels are reduced evenly and centred, smaller ones centred."""
    assets = make_assets(tmp_path, {"data.bin": {"data/at/at_text0.webp": wp((100, 30), (0, 0, 0, 0)), "data/at/at_text1.webp": wp((100, 30), (0, 0, 0, 0))}})
    donor = make_donor(tmp_path, {"data/System/systemTexture.pck": synth.make_pck({"at_text0.webp": wp((200, 40), RED), "at_text1.webp": wp((20, 10), RED)})})
    got = images.at_images(assets, donor)
    big, small = decode(got["data/at/at_text0.webp"]), decode(got["data/at/at_text1.webp"])
    assert big.size == small.size == (100, 30)
    assert big.getbbox() and big.getchannel("A").getbbox() == (0, 5, 100, 25)            # 200x40 reduced by 0.5 to 100x20 and centred
    assert small.getchannel("A").getbbox() == (40, 10, 60, 20)                           # 20x10 centred, not enlarged
    donor.close()
    assets.close()


# -------------------------------------------------------------- whole build --

@pytest.fixture
def quiet_build(monkeypatch):
    """The parts of the build that need the real pictures (LOOK sprites, minigame labels) are replaced by nothing."""
    monkeypatch.setattr(images, "look_images", lambda assets, donor: {})
    monkeypatch.setattr(images, "at_images", lambda assets, donor: {})


def test_whole_files_come_from_the_dump_except_what_android_builds_differently(tmp_path, quiet_build):
    """SPEC-016/R-1: the English (or translated) files replace the Android ones, except the exclusive packages and credits and the atlas package."""
    english = {"data/a.webp": wp((8, 8), RED), "data/b.webp": wp((8, 8), RED), "data/System/config.pck": synth.make_pck({"x.webp": wp((8, 8), RED)}),
               "data/System/staffrole02.webp": wp((8, 8), RED), "data/System/systemTexture3.pck": synth.make_pck({"x.webp": wp((8, 8), RED)})}
    translated = {"data/b.webp": wp((8, 8), GREEN)}
    assets = make_assets(tmp_path, {"data.bin": {"data/a.webp": wp((4, 4), BLUE), "data/System/systemTexture3.pck": synth.make_pck({"x.webp": wp((4, 4), BLUE)})}})
    donor = make_donor(tmp_path, english, translated=translated)
    repl = images.build(make_pack(tmp_path), assets, donor, None, say=lambda *_: None)
    assert decode(repl["data/a.webp"]).getpixel((0, 0)) == RED
    assert decode(repl["data/b.webp"]).getpixel((0, 0)) == GREEN                         # the translated one wins over the English one
    assert "data/System/staffrole02.webp" not in repl                                    # the credits stay as the app has them
    assert "data/System/config.pck" not in repl                                          # not copied whole: an exclusive package the app does not even have here
    donor.close()
    assets.close()


def test_the_atlas_package_gets_the_atlas_only_for_accented_languages(tmp_path, quiet_build):
    """SPEC-016/R-9: the atlas entries are replaced only when an atlas is given; pictures of the pack never replace them; the rest is kept."""
    atlas_pack = synth.make_pck({"sysFont16.webp": wp((8, 8), RED), "sysFont16_2.webp": wp((8, 8), RED), "text_en.webp": wp((8, 8), RED),
                                 "other.webp": wp((8, 8), RED)})
    assets = make_assets(tmp_path, {"data3.bin": {"data/System/systemTexture3.pck": atlas_pack}})
    donor = make_donor(tmp_path, {"data/x.webp": wp((8, 8), RED)})
    new_atlas = synth.make_pck({"sysFont16.webp": wp((8, 8), GREEN), "sysFont16_2.webp": wp((8, 8), GREEN)})
    manifest = {"format": 1, "containers": {"android": {"data/System/systemTexture3.pck": {
        "text_en.webp": {"kind": "full", "file": "t.webp"}, "sysfont16.webp": {"kind": "full", "file": "t.webp"}}}}}
    pack = make_pack(tmp_path, manifest, {"t.webp": wp((8, 8), BLUE)})

    def entries(repl):
        return {images.base_name(pck.entry_name(e[0])): decode(e[1]).getpixel((0, 0)) for e in pck.read_pck(repl["data/System/systemTexture3.pck"])[1]}

    with_atlas = entries(images.build(pack, assets, donor, new_atlas, say=lambda *_: None))
    assert with_atlas["sysfont16.webp"] == GREEN and with_atlas["sysfont16_2.webp"] == GREEN         # the atlas of the language
    assert with_atlas["text_en.webp"] == BLUE and with_atlas["other.webp"] == RED                    # the pack's picture; the rest kept
    without = entries(images.build(pack, assets, donor, None, say=lambda *_: None))
    assert without["sysfont16.webp"] == RED and without["text_en.webp"] == BLUE
    donor.close()
    assets.close()


# -------------------------------------------------------------- containers --

def test_a_replaced_path_goes_into_every_container_that_holds_it(tmp_path):
    """SPEC-016/R-10: the later containers are updates of the first, and a path they share is replaced in all of them; the latest one is the one read."""
    assets = make_assets(tmp_path, {"data.bin": {"data/x.webp": b"v1", "data/y.webp": b"y"}, "data2.bin": {"data/x.webp": b"v2"}})
    assert assets.read("data/x.webp") == b"v2" and assets.containers_with("data/x.webp") == ["data.bin", "data2.bin"]
    done = assets.pack({"data/x.webp": b"new", "data/absent.webp": b"never"}, tmp_path / "out")
    assert done["data.bin"][1] == 1 and done["data2.bin"][1] == 1 and done["data3.bin"][1] == 0
    from riviera import sge
    for name in ("data.bin", "data2.bin"):
        with sge.Archive(tmp_path / "out" / name) as arc:
            assert arc.read_path("data/x.webp") == b"new"
    with sge.Archive(tmp_path / "out" / "data.bin") as arc:
        assert arc.read_path("data/y.webp") == b"y"
    assets.close()


def test_the_assets_apk_must_be_the_expansion_apk(tmp_path):
    """SPEC-013/R-1: a folder without the expansion APK, or with another one, is refused with a message that says what is missing."""
    with pytest.raises(AssetError, match="split_asset_expansion.apk"):
        AndroidAssets(tmp_path, tmp_path / "work")
    with zipfile.ZipFile(tmp_path / "split_asset_expansion.apk", "w") as z:
        z.writestr("assets/data.bin", b"x")
    with pytest.raises(AssetError, match="data2.bin"):
        AndroidAssets(tmp_path, tmp_path / "work")
