# SPEC-010: The accented letters in the font

See [PIPELINE.md](../PIPELINE.md#fonts) for how the engine builds its glyph table.

## Requirements

- **R-1** Every character Spanish needs has a cell: the accented letters and `ü ñ` are native to the engine's character string, and
  `¿` `¡` take over the cells of `Þ` and `Ð`.
- **R-2** The atlases of `systemTexture3.pck` grow from 37 to 43 rows and get a glyph in the cell of each new character; the other
  pictures of the package are not touched (not even re-encoded).
- **R-3** The patch of `main` swaps the two characters in the engine's string without changing its length, and writes the metrics of the
  new glyphs.
- **R-4** The metrics used to break lines know the new glyphs with their real width.
- **R-5** The characters of a text that have no cell, or a cell without a picture, are reported.
