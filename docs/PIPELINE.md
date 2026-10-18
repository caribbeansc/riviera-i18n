# How it works

Where the game keeps its text, fonts and pictures, how the toolkit changes them, and the traps found on the way. Everything
here was measured on the Switch v1.0.0 build (title id `01007D6025CB6000`, build id
`07432F4805A57F4527209EE4387072FB0F5D8A37`) unless it says otherwise. Android has its own chapter in
[ANDROID.md](ANDROID.md).

```
your dump ──► read the script ──► compose the Spanish ──► patch main (IPS) ──► mod folder
 (exefs, romfs)   (riviera.nso)      (riviera.compose)      (riviera.ips)      exefs/*.ips
                                                                                romfs/data.bin     ◄── font atlas   (riviera.font)
                                                                                romfs/data_en.bin  ◄── pictures     (riviera.images)
```

## The script

The whole script is in the executable (`exefs/main`, an NSO), in **one table of pointers** to UTF-8 strings in `.rodata`. The
pointers are `R_AARCH64_RELATIVE` relocations (`DT_RELA` via `MOD0`): to change where a string lives you change the addend of its
RELA entry. The table has 90 804 pointers in 41 blocks of the form `[4 empty][EN n][JP n][KR n][TC n]`, so 22 667 English rows
that line up with the Japanese, Korean and Chinese ones. [`riviera/nso.py`](../riviera/nso.py) finds the table and the blocks by
content, without fixed addresses.

A string is a list of **segments**. Every ASCII comma and every `V(id)` (a voice clip) opens one; `;` is a line break (a `\n`
inside `cN` colour segments). Markers stay in ASCII: `V(id)` voice, `cN` colour, `p1`/`p2` number slots, `%d`, `B1`/`B3` button
icons. The English writes everything in full-width characters (`Ｗｈａｔ’ｓ`) and **the engine converts ASCII to full-width when
it draws**, so a translation is plain ASCII, which is also shorter. Text commas are written full-width; `…` is `＿`; there is no `“`.

What the engine does with a string that you would not guess:

- **The separating comma IS drawn** in static text (a probe on the difficulty screen showed `bbbb,,` when a segment already ended
  in a comma; the English itself uses those commas: `[Nightmare], which is…`). A segment that is not the last of its chain must not
  end in a comma, and the English marks "this continues the previous one" with a leading space.
- **The engine runs printf on strings** before drawing them: a bare `%` followed by a space and a letter (`75% del`) became
  `Recupera 75 1252el MAX HP`. The English writes percentages with a full-width `％`; the encoder does the same.
- **`￥` is drawn as a sweat drop**, and has to be kept. `＠` has no glyph (a box): it is removed. `[` and `]` come out as `【】`.
- **Strings the code uses by itself** (file paths such as `/`, `sprintf` formats, labels drawn by the text routine such as `TARGET`
  or `GET ITEM`, debug names) share the `.rodata` with the table. They are never rewritten in place or reused as free space: the
  `/` once looked like a free Japanese string, was overwritten with an `A`, and the game died three seconds after booting.
  [`ips.code_targets`](../riviera/ips.py) finds them by scanning the code for `adrp` + `add`/`ldr`.

### Where the new strings go

[`ips.place`](../riviera/ips.py) rewrites a string in place if the new one fits and nobody else uses those bytes; otherwise it puts
it in free memory (the tails of strings that were shortened, and the Japanese, Korean and Chinese strings of the same rows, which
the game does not use while it runs in English) and changes the addend of its relocation. For the Spanish pack that is 16 465 rows
in place and 258 moved, with 2.8 MB to spare. After building the IPS patch it is applied to the image and every string is read back.

## Fonts

The engine builds, at start-up, a character → atlas-cell table from a 2 494-character string in `.rodata` (the index of a
character is its cell). The advance of a glyph is the width in its metrics entry + 1 (`x0, width, y offset`, 6 bytes each, in three
tables for cells 251-332 and the Latin-1 ranges); a space advances 32. This build cut the atlas to 37 rows although the string and
the metrics already cover the accented Latin-1 letters (cells 2204-2261 and 2378-2386), so those cells are empty.
[`riviera/font.py`](../riviera/font.py) grows the two atlases (`sysFont16.webp`, a soft-edged glyph, and `sysFont16_2.webp`, a glyph
with a grey outline, in `data/System/systemTexture3.pck` of `data.bin`) to 43 rows and draws the accented letters in their native
cells from the user's own base letters plus an accent. `¿` and `¡` do not exist in the game: they are written over the cells of `Þ`
and `Ð` (their character in the string and their metrics change). A character whose cell is not drawn shows as a blank, so the build
lists every character of the text that has no glyph.

## Boxes: the English decides

Every kind of text has its own box, and **a cap per block does not work**: one wide row inflated a whole block (block 26 to 1 833
units, 23 to 1 108, 37 to 2 358, when almost all of their rows fit in 800-900), and the Spanish came out wider than the real box.
[`riviera/compose.py`](../riviera/compose.py) deduces the boxes from the English, per kind of row, and breaks the Spanish at the
real glyph widths (the engine's unit is one full-width cell = 68, about 0.65 px on a 1280 px screen):

- **Dialogue** (blocks 11-21, 35) and every line with a voice clip are composed segment by segment. The text starts at about 686
  units when a big portrait sits on the left, and a page never goes past **two lines**: English never does (9 589 pages of one line
  and 8 469 of two) and a third line is cut at the bottom of the box and, in the message log, overlaps the next entry. **Switch**
  shifts a block that is wider than what is left to the right margin as a whole to the left (the right end stays on screen and
  covers the portrait), so lines of up to about 1 790 units show whole; the composer widens a line up to 1.4 times the English cap
  (`--soft`) only to avoid a third line. At 1.12 there would be 102 pages of three lines. **Android** cuts at the right from about
  1 206 units instead (see [ANDROID.md](ANDROID.md)).
- **Place descriptions** (22-30) share one box, the one of the English 5-line rows (780-892 units), and fit it strictly. Items (36):
  891 units × 7 lines. Battle tips (31): 1 500-1 650 × 3.
- **Interface text** (blocks 0-9, 34, 37-39). One line: the cap of the block (and 1.5 × the English, or +200, when the English is
  short). Several lines: **the same lines as the English**, in a box of the widest English line × 1.25 (× 1.15, 1.3, 1.5 when the
  Spanish does not fit those lines). With the typical box of the family alone, 17 rows of block 37 ended up on one long line of
  1 600-1 900 units that did not get cut on Switch but hugged the edges of the screen and, on Android, was cut off.
  Looking at the whole capture, not only at whether the text is complete, is the lesson.
- **Bullet lists** (`・`, the difficulty and mode descriptions): one bullet per line, in the common box of the lists of the block.
- **Option names and buttons are interface even when they read like sentences** (the four pill-shaped "Check ..." buttons of the
  battle information menu): they stay English, while the help line that goes with them is Spanish.

The confirmation box of the game is as wide as `max(905, widest line + 40)`, sticks to the right and centres its text: a
1 597-unit single line stretched it to the edge of the screen. That is another reason to keep the English lines.

## Pictures

`data_en.bin` has the pictures with text; `data.bin` the shared ones. Inside are `.pck` packages (`u32 count`, `u32 start of
data`, 72-byte entries: a 64-byte name, size and offset) of WebP images with alpha. The engine draws every picture **at its own
native size**, so a translated picture may be wider, narrower or taller than the original. The pack stores two kinds of picture
([specs/SPEC-003](specs/SPEC-003-image-delta.md)): text drawn on an empty canvas, stored whole, and pictures that keep panels or a logo,
stored as an overlay plus a mask over the user's picture. The renderer for the first kind (`tools/render_images.py`) calibrates
fonts, sizes and compression by measuring the original, and needs macOS fonts: it is for people who redraw the art, not for the build.

The containers (`data*.bin`) are described in [specs/SPEC-001](specs/SPEC-001-containers.md): an index obfuscated with
`MD5(rot13("InfoData"))`, files obfuscated with the key of their own name, zlib inside.

## Traps

- **Check a rule of the engine with a probe before you write it down.** For hours it was "known" that the separating comma was not
  drawn; a probe string showed `bbbb,,`. Probes are read on the screen capture, not in the string.
- **A rule that "does not cut" is not "looks right".** See the interface boxes above.
- **A sentence can be a button.** The form-of-a-sentence test let one of the pill-shaped "Check ..." buttons through; it is interface.
- **Do not trust a documented layout until you have seen it drawn**: the length of a line and the number of lines are two different
  limits, and the box of a screen is not the box of the block.
- If the game dies seconds after booting with "invalid memory region", suspect a patch to `main` and bisect with variants of the
  mod instead of guessing.
- A build you have not seen is refused (`riviera/builds.py`): the font string and the metrics tables are found by address.

## The other platforms

**Android** (v1.0.4): the script is in `libapp.so`, in Japanese, and the text engine advances a fixed cell per character. The build
aligns the app's text slots with the Switch rows, writes the proportional engine and the glyphs, and patches the app:
[ANDROID.md](ANDROID.md). **PC** (v1.0.3) is the same engine compiled for English; it is not covered yet.
