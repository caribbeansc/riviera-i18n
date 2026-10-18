# SPEC-005: Copyright-safe translation keys

The script of the game is the publisher's copyrighted work. This repository must be redistributable, so **it stores no source text
at all**: not even as a comment. What it stores is a *reference* to a string plus the translation of it:

```json
{"k": "a9993e364706816a", "t": ["Pulsa el botón B1"]}
```

`k` is a fingerprint of the string as the game stores it (the English for Switch, the Japanese for the strings that exist only on
Android). It identifies a string the user already has; it does not carry it. The text of the game itself only exists under `work/`
on the user's machine, which is in `.gitignore`.

## Requirements

- **R-1** `fingerprint(raw)` is the first 16 hex digits of the SHA-1 of the UTF-8 bytes. It is stable across runs and platforms and
  has a fixed length whatever the input.
- **R-2** An entry is `{"k": fingerprint, "t": [segments]}` (a string for the Java strings of the Android app) and nothing from the game.
  An Android-only string whose English is exactly a string of the official Switch script is stored as `{"k": fingerprint, "ref": fingerprint of
  that Switch string}` instead of its text, and the build reads the text from the user's own Switch dump (SPEC-014/R-9).
- **R-3** Keys are unique within a file.
- **R-4** No file under `langs/` may contain a character in the ranges CJK punctuation (U+3000-303F), kana, CJK ideographs, Hangul
  or halfwidth and fullwidth forms (U+FF00-FFEF), except the markers that the game writes into its own English and that
  translations keep: `・` (bullets), `￥` (the sweat drop), and the placeholder and inscription characters `あ` and `、`. This is a
  test, not a guideline.
- **R-5** Checking a pack against a dump compares only the strings the dump has; the segments and markers of each must match.
- **R-6** `sync` refuses to write a pack that contains text that looks like the game's own.
- **R-7** `work/` and `build/`, where the game's text and the generated mods live, are in `.gitignore`.
- **R-8** `sync` keeps the entries the current dump does not contain, so translating from one dump never deletes the work done against
  another; a pack can support several versions of the game.
