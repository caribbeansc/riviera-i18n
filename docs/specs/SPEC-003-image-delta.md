# SPEC-003: Translated artwork: full pictures and deltas

Some text is baked into pictures. Shipping the translated pictures would ship the game's artwork, so a language pack stores two kinds
of picture, listed in `langs/<code>/images/manifest.json`:

```json
{"format": 1, "containers": {"data_en.bin": {"data/event/demo1.pck": {
  "story_00.webp":  {"kind": "full",  "file": "data_en/data/event/demo1.pck/story_00.webp", "base": "<sha1 of the original>"},
  "1000year.webp":  {"kind": "delta", "overlay": ".../1000year.png", "mask": ".../1000year.mask.png", "base": "<sha1>"}}}}}
```

* **full**: text drawn by this project on an empty, transparent canvas. It replaces the game's picture as it is, and may have another
  size (the engine draws every picture at its own native size).
* **delta**: an edit of a picture that keeps panels, buttons or a logo. Only the difference is stored: an RGBA overlay (the final value
  of every changed pixel) and an `L` mask (255 where a pixel changed). The mask is needed because a pixel can change *to*
  transparent. The builder rebuilds the picture as the user's original + the delta.

The pictures of the Android build extend the manifest with an `android` section and a third kind, `layer`: see
[SPEC-016](SPEC-016-android-artwork.md). There, the label a picture replaces is erased at build time from the user's own copy (R-6, R-12),
so the pack stores no mask, no overlay and no silhouette of it.

## Requirements

- **R-1** `make_delta(original, translated)` returns `(overlay, mask, changed fraction)` for pictures of the same size, and refuses
  different sizes. The overlay is transparent outside the mask.
- **R-2** A pixel counts as changed if any of R, G, B or A differs, **except** that two fully transparent pixels are equal whatever
  their RGB; a pixel can change to transparent and that is recorded.
- **R-3** `apply_delta(original, *make_delta(original, translated)[:2])` reproduces `translated` exactly, alpha included.
- **R-4** If nothing changed, the mask is empty and the fraction is 0.
- **R-5** The manifest lists, per container, per package, the entries with their `kind` and the files they need; `build_package`
  rebuilds a package from the original package and those entries, leaving the other entries as they are.
- **R-6** A `full` picture may have another size than the original it replaces.
- **R-7** A delta made at one size is scaled to the size of the picture it is applied to, never cropped.
- **R-8** Every entry carries `base`, the SHA-1 of the original picture it was made against.
- **R-9** If the original in the user's package is not the one `base` names, the build warns (a different version of the game); an entry
  the package does not have is an error.
- **R-10** `translated_packages` builds every translated package of a container from the user's own copy of it.
- **R-11** `make_delta(..., rect=True)` uses the bounding rectangle of the changes as the mask. The rebuilt picture is the same, but the mask no
  longer traces the glyphs of the text that was erased and redrawn (the exact mask of such a label is a silhouette of the original one), so a
  delta that is published uses it.
