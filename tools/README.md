# Contributor tools

Scripts for people who add or redraw the artwork of a language, or who work on the toolkit itself. **None of them is part of the
build**: `python rpl.py ...` never runs them, and a player needs none of them (the build reads the pictures from
`langs/<code>/images/`).

| File | What it does |
|---|---|
| [`render_images.py`](render_images.py) | Draws the translated pictures of a language from a spec, with macOS system fonts, measuring each original picture so that the new text has the same size, compression and margins. Needs a Mac. |
| [`compare_images.py`](compare_images.py) | A contact sheet of the original and the redrawn pictures, to check them by eye. |
| [`ocr.swift`](ocr.swift) | macOS OCR (Vision): reads the English of the original pictures, for the calibration labels that `render_images.py` needs. Needs a Mac and the Xcode command line tools. |
| [`images_pack.py`](images_pack.py) | Stores the redrawn pictures in a language pack, as full pictures and as deltas over the originals. Runs anywhere. |
| [`android/`](android/) | Android build helpers. |

## The artwork workflow

About 200 pictures carry text baked in: the intro, the scene titles, the captions of the illustrations, the chapter cards, the
explanation of every option of the configuration screen. Without your own version they stay in English. The pack never holds a
picture of the game: text drawn on an empty canvas is stored whole, and an edit of a picture that keeps panels or a logo is stored
as an overlay plus a mask over **your** original ([SPEC-003](../docs/specs/SPEC-003-image-delta.md)).

```
python rpl.py unpack ──► work/switch/data_en/ ──► render_images.py ──► work/switch/rendered/ ──► images_pack.py ──► langs/<code>/images/
                             │                          ▲                  │
                             └──► ocr.swift ──► labels ─┘                  └──► compare_images.py ──► a contact sheet (PNG)
```

Run everything from the root of the repository. `work/` is git-ignored: it is where the game's own pictures and text stay. With
`RPL_HOME` set, `work/` lives under it and the default paths of the tools follow.

### 1. Unpack the originals

```
python rpl.py unpack
```

This writes `work/switch/data_en/` from your own dump (`data/event/*.pck`, `data/System/*.pck`...). It is what `--originals` takes.

### 2. Make the calibration labels (only if the specs need them)

The styles that measure the original picture (`auto`, `patch`, `lines`, `flat_*`, `skillname`) need its English text, to know how big
and how compressed its letters are; the `poem` style needs the poem's nine English lines, because it cuts its letters out of the
picture. The Spanish specs need them for `System/boost.pck` and `System/config.pck` (`explanations.json`) and for the poem
(`cutin_text.webp` in `System/systemTexture.pck`). The styles that only draw text (`story`, `title`, `caption`, `chapter`,
`mapname`, `chrcopy`, `year`) need none.

The labels are one JSON file, `{package: {entry: english text}}` (`--labels`, by default `work/switch/ocr/en_labels.json`):

```json
{
  "System/config.pck": {"some_label.webp": "The English text of that picture"},
  "System/systemTexture.pck": {"cutin_text.webp": "line 1|line 2|...|line 9"},
  "": {"some/loose_file.webp": "A picture that is a loose file, by its path"}
}
```

Package and entry names are the ones the spec uses; the lines of a multi-line label (and of the poem) are joined by `|`.
**This file is the game's own text: it stays under `work/` and is never committed.**

`ocr.swift` prints `file<TAB>text` for the pictures it is given. To fill the labels file from whole packages, build it, save the script
below as `work/make_labels.py` and run it:

```
mkdir -p work/switch/ocr
swiftc -O tools/ocr.swift -o work/switch/ocr/ocr
python work/make_labels.py System/boost.pck System/config.pck
```

```python
# work/make_labels.py: adds the English text of every picture of some packages to the labels file (on a Mac, from the repository root).
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from riviera import images, pck  # noqa: E402
from riviera.config import user_dir  # noqa: E402

switch = user_dir() / "work" / "switch"
labels_path = switch / "ocr" / "en_labels.json"
labels = json.loads(labels_path.read_text("utf-8")) if labels_path.exists() else {}
for package in sys.argv[1:]:
    folder = switch / "ocr" / "png" / package
    folder.mkdir(parents=True, exist_ok=True)
    for raw, blob in pck.read_pck((switch / "data_en" / "data" / package).read_bytes())[1]:
        try:
            picture = images.decode(blob)
        except OSError:                                               # not a picture (the empty dummy.dat placeholders)
            continue
        flat = Image.new("RGBA", picture.size, (40, 40, 90, 255))     # opaque: Vision reads nothing in dark text on transparency
        flat.alpha_composite(picture)
        flat.convert("RGB").save(folder / (pck.entry_name(raw) + ".png"))
    run = subprocess.run([str(switch / "ocr" / "ocr"), *map(str, sorted(folder.glob("*.png")))],
                         capture_output=True, text=True, check=True)
    for line in run.stdout.splitlines():
        name, _, text = line.partition("\t")
        labels.setdefault(package, {})[name.removesuffix(".png")] = text
labels_path.parent.mkdir(parents=True, exist_ok=True)
labels_path.write_text(json.dumps(labels, indent=1, ensure_ascii=False) + "\n", "utf-8")
```

OCR is a starting point, not the truth. Read the labels against the pictures:

- It misreads symbols. For a `patch` entry the label is only the words that the entry rewrites (inside its `tbox`), not the ones the
  picture keeps.
- It joins the lines it reads with ` / `; the labels of the `lines` style join them with `|`.
- It cannot read the poem (a pixel font). Type its nine lines by hand, spelled exactly as the picture spells them: the letters are
  matched by count, so a wrong spelling stops the render with a message that names the line.

### 3. Render

```
python tools/render_images.py --originals work/switch/data_en --labels work/switch/ocr/en_labels.json \
    --spec langs/es/images/specs/narrative.json --spec langs/es/images/specs/explanations.json --out work/switch/rendered
```

A spec says which picture gets which text in which style: `{"event/demo1.pck": {"story_00.webp": {"estilo": "story", "texto": "..."}}}`.
The keys `estilo` and `texto` are Spanish on purpose (the shipped specs use them) and a spec holds only your text, never the game's.
`python tools/render_images.py --help` explains the specs, the labels and every style. Without the macOS font a style needs, the tool
stops and names the font.

### 4. Check by eye

```
python tools/compare_images.py --originals work/switch/data_en --rendered work/switch/rendered \
    --spec langs/es/images/specs/narrative.json --out work/switch/compare.png story_00 chap1
```

The sheet shows every original with the new picture under it; the words at the end pick pictures by name.

### 5. Store them in the pack

```
python tools/images_pack.py --code es --container data_en.bin --originals work/switch/data_en --rendered work/switch/rendered \
    --spec langs/es/images/specs/narrative.json --spec langs/es/images/specs/explanations.json
```

This fills `langs/es/images/` and its `manifest.json`; `python rpl.py switch build es` then puts the pictures in the mod. For a new
language, copy the two specs to `langs/<code>/images/specs/`, translate the `texto` values and keep everything else.

## Notes

- Drawing is deterministic for a given Pillow, FreeType and set of fonts: the Spanish specs give the same bytes with Pillow 12.2.0 and
  13.0.0. An older Pillow (10.4) writes other WebP bytes and, with its older FreeType, two pictures differ by a few pixels. That is why
  the pack stores the pictures themselves and the build never redraws anything.
- `tests/test_tools_render.py` covers `render_images.py` with synthetic pictures; the tests that draw skip themselves where the font
  is missing.
