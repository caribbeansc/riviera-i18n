"""tools/render_images.py, the contributor tool that draws the translated pictures.

It draws with macOS system fonts, so the tests that draw skip themselves where the font is missing (Linux, Windows, a Mac without
it). The ones that only check the errors need no font. Nothing here comes from the game: the packages and pictures are synthetic.
"""

import io
import json
import struct
import sys
from pathlib import Path

import pytest
from PIL import Image

import synth
from riviera import pck

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import render_images  # noqa: E402

TIMES = Path(render_images.FONTS["times_bold"][0])
needs_font = pytest.mark.skipif(not TIMES.is_file(), reason=f"needs the macOS font {TIMES.name}")


def chunks(blob: bytes) -> list[bytes]:
    """The chunk tags of a WebP file: a lossless picture carries ``VP8L``, a lossy one ``VP8 ``."""
    assert blob[:4] == b"RIFF" and blob[8:12] == b"WEBP"
    tags, pos = [], 12
    while pos + 8 <= len(blob):
        size = struct.unpack_from("<I", blob, pos + 4)[0]
        tags.append(blob[pos:pos + 4])
        pos += 8 + size + (size & 1)
    return tags


def is_lossless(blob: bytes) -> bool:
    tags = chunks(blob)
    return b"VP8L" in tags and b"VP8 " not in tags


def originals_with(tmp_path: Path, entries: dict) -> Path:
    """A folder laid out like ``python rpl.py unpack`` writes it, with one synthetic package, ``event/demo.pck``."""
    folder = tmp_path / "originals" / "data" / "event"
    folder.mkdir(parents=True)
    (folder / "demo.pck").write_bytes(synth.make_pck(entries))
    return tmp_path / "originals"


def render(tmp_path: Path, originals: Path, entry: dict, labels: dict | None = None) -> int:
    """Run the tool on one entry of ``event/demo.pck``; the labels file is only written when there are labels."""
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"event/demo.pck": entry}), encoding="utf-8")
    labels_file = tmp_path / "labels.json"
    if labels is not None:
        labels_file.write_text(json.dumps(labels), encoding="utf-8")
    return render_images.main(["--originals", str(originals), "--spec", str(spec), "--out", str(tmp_path / "out"),
                               "--labels", str(labels_file)])


def rendered(tmp_path: Path) -> dict:
    """``{entry name: bytes}`` of the package the tool wrote."""
    _, ents = pck.read_pck((tmp_path / "out" / "data" / "event" / "demo.pck").read_bytes())
    return {pck.entry_name(name): blob for name, blob in ents}


@needs_font
def test_a_story_line_is_a_lossless_picture_of_the_canvas_height():
    style = render_images.STYLES["story"]
    im = render_images.render_story("¿Qué hora es, señor?", style)
    assert im.mode == "RGBA" and im.size[1] == style["height"] == 64            # the height is fixed, the width follows the text
    assert 0 < im.size[0] <= style["maxw"]
    blob = render_images.encode_webp(im)
    assert is_lossless(blob)
    back = Image.open(io.BytesIO(blob)).convert("RGBA")
    assert back.size == im.size and back.getchannel("A").tobytes() == im.getchannel("A").tobytes()
    raw = back.tobytes()
    ink = {raw[i:i + 3] for i in range(0, len(raw), 4) if raw[i + 3] == 255}
    assert ink == {bytes(style["fill"])}                                         # drawn in the colour of the style


@needs_font
def test_a_package_is_redrawn_and_its_other_pictures_are_left_alone(tmp_path):
    keep = synth.webp((4, 4), (1, 2, 3, 255))
    originals = originals_with(tmp_path, {"story_00.webp": synth.webp((8, 8)), "keep.webp": keep})   # a synthetic canvas
    assert render(tmp_path, originals, {"story_00.webp": {"estilo": "story", "texto": "Hola, mundo."}}) == 0
    pictures = rendered(tmp_path)
    assert list(pictures) == ["story_00.webp", "keep.webp"]                      # same entries, same order
    assert pictures["keep.webp"] == keep
    assert is_lossless(pictures["story_00.webp"])
    assert Image.open(io.BytesIO(pictures["story_00.webp"])).size[1] == render_images.STYLES["story"]["height"]


@needs_font
def test_the_labels_file_calibrates_a_label_on_the_original(tmp_path):
    canvas = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    canvas.paste((255, 255, 255, 255), (10, 8, 90, 30))                          # the "ink" of a synthetic label
    buf = io.BytesIO()
    canvas.save(buf, "WEBP", lossless=True)
    originals = originals_with(tmp_path, {"label.webp": buf.getvalue()})
    entry = {"label.webp": {"estilo": "auto", "font": "times_bold", "texto": "Hola, amigo"}}
    assert render(tmp_path, originals, entry, labels={"event/demo.pck": {"label.webp": "Hello, friend"}}) == 0
    blob = rendered(tmp_path)["label.webp"]
    assert is_lossless(blob)
    assert Image.open(io.BytesIO(blob)).convert("RGBA").getchannel("A").getbbox() is not None


def test_a_style_that_calibrates_on_the_original_needs_its_label(tmp_path, capsys):
    canvas = synth.webp((40, 12), (255, 255, 255, 255))
    originals = originals_with(tmp_path, {"label.webp": canvas})
    assert render(tmp_path, originals, {"label.webp": {"estilo": "flat_tahoma", "texto": "Hola"}}) == 1
    err = capsys.readouterr().err
    assert "event/demo.pck/label.webp" in err and "English" in err and "labels" in err


def test_a_missing_font_is_reported_by_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(render_images.FONTS, "times_bold", (str(tmp_path / "gone" / "Times.ttf"), 0))
    originals = originals_with(tmp_path, {"story_00.webp": synth.webp()})
    assert render(tmp_path, originals, {"story_00.webp": {"estilo": "story", "texto": "Hola"}}) == 1
    err = capsys.readouterr().err
    assert "times_bold" in err and "macOS" in err
    assert not (tmp_path / "out" / "data" / "event" / "demo.pck").exists()      # nothing is written half done


def test_an_unknown_style_is_reported(tmp_path, capsys):
    originals = originals_with(tmp_path, {"story_00.webp": synth.webp()})
    assert render(tmp_path, originals, {"story_00.webp": {"estilo": "sparkles", "texto": "Hola"}}) == 1
    assert "sparkles" in capsys.readouterr().err
