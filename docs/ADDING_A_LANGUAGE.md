# Adding a language, or fixing a line

A language is a folder under `langs/`. For a language that uses the letters Spanish already has (see "Letters" below) you do not need
to touch any Python.

## 1. Create the pack

```
python rpl.py newlang fr --name "Français" --like es
```

You get `langs/fr/lang.json` (copied from Spanish, with your code and name) and an empty `langs/fr/text.jsonl`. The **scope** of what to
translate is the key list of the pack named by `--like`: Spanish translates the story and everything that explains something and leaves
menus, interface and names in English (see the README). Any other choice of scope is a different pack.

## 2. Tell the tool what your language needs

Edit `langs/fr/lang.json`:

```json
{
  "code": "fr", "name": "Français", "english_name": "French", "mod_name": "Riviera_FR", "scope": "spanglish",
  "font": { "accents": true },
  "platforms": { "switch": { "soft": 1.4 }, "android": { "soft": 1.12 } },
  "validation": { "extra_chars": "àâçéèêëîïôùûüÿœ«»…" }
}
```

- **`font.accents`**: the game's font lost its accented letters in this build; this asks the toolkit to draw the ones it knows.
- **`platforms`**: what the pack covers. `soft` is how far a dialogue line may widen before it needs a third line (1.4 on Switch;
  1.12 on Android, whose engine cuts instead of shifting). Leave a platform out and the pack will not build for it.
- **`validation.extra_chars`**: every non-ASCII character your language may use. Anything else is reported, which is how typos and
  stray characters are caught. Characters that the game's own English uses (symbols) are fine in the translation of that string.
- **`validation.forbidden`**: a list of `{"pattern": regex, "message": ...}` that `validate` rejects (for example a term the
  glossary forbids).

### Letters

The Latin-1 letters already have cells in the engine's character string and metrics; the pictures of those cells are missing, and
`riviera/font.py` draws them from the base letter plus an accent: acute (`á é í ó ú`), diaeresis (`ü`), tilde (`ñ`) and the
turned `¿ ¡`. A language that needs more (`à ç ê ô ß`...) needs the extra accent shapes and the entries in `BASE` of
`riviera/font.py`: a small, contained change, and the place to look at if a character comes out blank (the build lists those).

## 3. Get the source text

```
python rpl.py extract fr
```

This reads **your** dump and writes `work/switch/lang/fr/units.jsonl`, one string per line, with the readable English, its voice or
colour tags, where it first appears, and your translation `t` (empty at first):

```json
{"k": "…", "block": 12, "row": 3, "rows": 1, "tags": ["V(112b_0003)", "V(112b_0004)"],
 "en": ["First segment", "second segment"], "t": null}
```

`work/` is git-ignored: that is the only place the game's text lives, and it stays on your machine.

## 4. Translate

Fill in `t` with a list of **exactly as many segments as `en`**. Rules that matter (the validator checks them):

- Keep `p1`, `p2`, `%d`, `{}`, `[Names]`, `B1` / `B3`, `c1`, `￥` and the symbols exactly as they are.
- Do not use `;`, `|`, tabs or line breaks: the composer breaks lines at the real glyph widths.
- A segment that continues the previous one must not end in a comma (the engine draws the comma that separates them).
- Copy silences (`…`, `…?`) as they are.
- Names, menu options and anything the glossary keeps in English stay in English inside your text.
- Be short: the boxes are the English ones, about 1.3 times the English length is the most that fits.

Spanish has the style rules and the glossary in [langs/es/GLOSSARY.md](../langs/es/GLOSSARY.md); write one for your language.

## 5. Check, publish, build

```
python rpl.py validate fr     # markers, segments, characters; with your dump also: does everything fit its box?
python rpl.py sync fr         # work/ -> langs/fr/text.jsonl, keys and translations only
python rpl.py switch build fr
python rpl.py switch install fr
```

`sync` is what makes your work committable: it writes only fingerprints and translations, keeps the entries you already had for other
versions of the game, and refuses text that looks like the game's own.

## 6. Artwork with text baked in (optional)

About 200 pictures carry text (the intro, chapter cards, captions of the CG, the explanations of the options). Without your own
version they stay in English. To make them:

1. Draw each one at a size that suits the text (the engine draws a picture at its own size). `tools/render_images.py` draws them from a
   small spec (text, font, size); it needs macOS fonts and the calibration labels of your dump, so most people will prefer to draw
   them in an image editor.
2. Put the originals of your dump in one folder tree and your pictures in another, with the same layout
   (`python rpl.py unpack` writes the originals under `work/switch/data_en/`), and run
   `python tools/images_pack.py --code fr --originals work/switch/data_en --rendered <your folder> --spec <your spec>`. It stores
   text drawn on an empty canvas as it is and edits of a picture that keeps panels as an overlay plus a mask
   ([specs/SPEC-003](specs/SPEC-003-image-delta.md)).

## 7. Open a pull request

```
python rpl.py doctor         # confirms no game text made it into langs/
git add langs/fr
git commit -m "Add French translation"
```

Please do not commit `work/`, `build/` or `rpl.config.json`; `.gitignore` already excludes them. See
[../CONTRIBUTING.md](../CONTRIBUTING.md).
