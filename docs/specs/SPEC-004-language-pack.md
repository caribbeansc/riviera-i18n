# SPEC-004: Language pack layout

A language is a directory. Adding one must not require touching a line of Python.

```
langs/<code>/
├── lang.json            metadata and per-platform layout parameters
├── text.jsonl           the script: {"k": fingerprint, "t": [segments]} per line
├── images/              manifest.json + the pictures (SPEC-003)
├── android/             strings and pictures that exist only in the Android app
└── GLOSSARY.md          optional, human-facing terminology rules
```

`<code>` is a BCP-47-ish lowercase tag: `es`, `en`, `pt-br`.

```json
{"code": "es", "name": "Español", "english_name": "Spanish", "mod_name": "Riviera_ES", "scope": "spanglish",
 "font": {"accents": true},
 "platforms": {"switch": {"soft": 1.4}, "android": {"soft": 1.12}},
 "validation": {"extra_chars": "áéíóúÁÉÍÓÚñÑüÜ¡¿…", "forbidden": [{"pattern": "\\bMagos\\b", "message": "use Magi"}]}}
```

`platforms` says which platforms the pack covers and carries their layout parameters (`soft`: how far dialogue lines may widen
before a third line is needed). `font.accents` asks for the accented letters to be added to the game's font.

## Requirements

- **R-1** `discover` lists every directory under `langs/` that has a readable `lang.json`, sorted by code; nothing else is scanned.
  Asking for a pack that does not exist names the ones that do.
- **R-2** `code`, `name` and `mod_name` are mandatory; a pack missing one fails to load with a message naming the file and the field.
- **R-3** `code` must match `^[a-z]{2,3}(-[a-z0-9]{2,8})*$` and `mod_name` must be a single folder name with no separators.
- **R-4** Every other field is optional and has a default: no platforms, no font patch, no validation rules, an empty script.
- **R-5** The Spanish pack ships `lang.json` and its `GLOSSARY.md`.
