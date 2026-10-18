# SPEC-016: The artwork of the Android build

Most pictures of the Android app exist in the Switch containers too, so the Android pictures are made **from the user's Switch dump**
(`data_en.bin`; for a translated language, the translated packages of [SPEC-003](SPEC-003-image-delta.md)). What the dump cannot give
(labels of screens only Android has, drawn with fonts that this repository does not ship) comes with the language pack in
`langs/<code>/android/images/manifest.json`, in the formats of SPEC-003 plus `layer`:

* `full`: text on an empty canvas of the size of the original; `delta`: only the changed pixels over the user's original;
* `layer`: `{"kind": "layer", "size": [w, h], "ops": [...], "bleed": [r, g, b], "encode": "exact" | "plain"}`. An empty transparent canvas
  receives, in order, `{"op": "layer", "file": "x.png", "at": [x, y]}` (a picture of the pack: our text), `{"op": "copy", "from": "<entry>" | null,
  "box": [l, t, r, b], "to": [x, y]}` (a piece of the user's own original; `null` = the same entry) or `{"op": "erase_enclosed"}` (the label
  printed on a flat-coloured button is painted over with the colour of the button, found from the user's own pixels). `bleed` is the RGB of
  the transparent pixels; `encode` says how the result is saved (`exact` keeps the colour of the transparent pixels).

The pack never stores the Japanese of the app's pictures, not even as a shape: what was printed on a button is erased when the app is built, and
`delta` masks are plain rectangles (SPEC-003/R-11).

The manifest lists them under `containers.android`, per package (a loose file is its own package, entry `*`), keyed by the lower-case
name of the entry. Pictures are built as follows.

## Requirements

- **R-1** Every file of the Switch `data_en.bin` replaces the Android file of the same path, with the translated package where the pack has
  one, except the packages Android builds differently, the two credit pictures, and the font atlas package.
- **R-2** In a package only Android has (or builds differently), each picture is replaced **by name** with the Switch one: the same size is
  taken, another size is taken at its own size (the engine draws every picture at its native size) unless the Android picture is at least
  256x160 (it may be a sprite sheet with coordinates in the code, so it is kept); a picture the pack or the code makes wins over the Switch one.
- **R-3** The pictures that need work are those of a fixed list of files, compared with the Switch ones of the same name: `same` (identical),
  `same_size`, `other_size` or `no_counterpart`. Those with `other_size` or `no_counterpart` are classified by path patterns (first match wins):
  omit (already English or no text), generate (the pack draws it), fit (scaled to the exact size), copy (the Switch picture as it is),
  and otherwise height.
- **R-4** `height` scales the Switch picture to the height of the Android one keeping the width, with premultiplied alpha; the labels of the
  options screen are squeezed into their column (430 and 892 units).
- **R-5** `full`, `delta` and `layer` pictures of the pack replace the original entry; an entry the package does not have is an error; an
  original that is not the one `base` names (a different version of the app) is reported as a warning.
- **R-6** A `layer` is composed as described above and saved as lossless WebP (keeping the colour of the transparent pixels unless `encode` is
  `plain`). `erase_enclosed` paints the text that sits on the flat body of a button (the pixels the flood from the corner cannot reach, grown by two
  pixels) with the colour of the body and leaves the outline and the shadow as they are.
- **R-7** The LOOK sprites (corner indicator and centre notice) are drawn from the four letters of the Switch picture of LOOK, with the canvas,
  the colours and the vertical position measured from the user's QUEST sprites; four letters are required.
- **R-8** The labels of the button-press minigames are the Switch labels fitted into the canvas of the Android files: reduced evenly if bigger,
  centred if smaller.
- **R-9** In the package of the font atlas the atlas entries are replaced only for a language that patches the font; pictures of the pack or
  the code never replace the atlas, and the other entries of the package are kept.
- **R-10** A path is replaced in **every** container that holds it (the later containers are updates of the first).
- **R-11** The files of `langs/<code>/android/images/` are exactly those the manifest names, and the manifest only uses the kinds above.
- **R-12** No picture of the pack traces the Japanese of the app: a `delta` of an Android picture has a solid rectangular mask, and the pictures
  that used to carry the silhouette of a label (the arrows and bars of the backup screen) are `layer` entries that copy pieces of the user's picture
  and erase the label when the app is built.
