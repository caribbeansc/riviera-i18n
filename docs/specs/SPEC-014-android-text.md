# SPEC-014: The script in the Android library

`libapp.so` carries the script as Japanese strings that the code reaches through pointers (`R_AARCH64_RELATIVE` relocations, the *slots*).
The build gives each slot the text of the Switch row that holds the same sentence: the English of the dump, or the translation of the
pack composed for the real glyph widths ([SPEC-009](SPEC-009-composer.md)). Text that exists only in Android has its own file,
`langs/<code>/android/text.jsonl`:

```json
{"k": "<fingerprint of the Japanese>", "t": ["segment", "segment"], "cap": 1700}
{"k": "...", "ref": "<fingerprint of a string of the Switch script>"}
{"k": "...", "t": [{"ref": "<fingerprint>", "seg": 0}, "own text"], "force": true}
{"k": "...", "t": ["message"], "lit": true}
```

`t` is the list of segments (as many as the Japanese has), `cap` the widest line allowed, `lit` marks a string the code uses directly
(rewritten in place), `force` replaces a slot that did align with a Switch row (its Japanese is identical but the Switch text talks about
physical buttons). `ref` is a reference to the official English: see R-9.

## Requirements

- **R-1** The slots, sorted by address, are aligned with the rows of the Switch table **by order**: the anchors are the slots whose Japanese
  appears in exactly one row, the longest increasing chain of them is kept, and a repeated text takes the first row after the previous
  one. A slot is only assigned a row with **identical** Japanese; nothing is matched by similarity. What has no row is Android-only text.
- **R-2** The new strings go into one segment appended to the file, by turning the `PT_NOTE` header into a `PT_LOAD` (read and execute).
  The first `RESERVE` bytes are left zero for the hooks ([SPEC-015](SPEC-015-android-hooks.md)); equal texts share one copy. The
  relocation addend and the value stored in the file of every slot are redirected; the Japanese strings stay where they were.
- **R-3** A row the pack does not translate keeps the English of the donor.
- **R-4** In dialogue (blocks 11-21 and 35) no page has more than two lines: the box and the message log are made for two, and the English
  never goes past them. A page the composer left in three is split again in two with the smallest cap that does it.
- **R-5** A label or message of the interface whose English has two or more lines goes back to that many lines when a translated line is wider
  than 1.25 times the widest English one (a box made for the English lines would cut it). Lists of `・` bullets are left alone.
- **R-6** An Android-only text is composed like the Switch text: the tags and separators of the Japanese are kept, the segments of `t` must be
  as many as the Japanese has (otherwise it is an error), lines are broken at the real widths with the cap of the entry (without one: the
  longest Japanese line times 66; a voiced or tagged segment uses the dialogue band), and a `%s` is measured as a three-digit number.
- **R-7** An Android-only entry replaces only the slots with no Switch counterpart, except when it carries `force`.
- **R-8** A literal is written over the original string, zero padded; one that needs more bytes than the original has is an error.
- **R-9** The pack carries no line of the official script. An entry whose text is the official English holds a reference instead: `ref` for
  the whole entry, or `{"ref", "seg"}` items inside `t`. The build resolves it with the strings of the user's Switch dump; with no dump, or
  a reference the dump does not have, it fails with a message that says which entry.
- **R-10** A few plain labels that the library already has in English and that Switch writes differently (the mode is called LOOK, not
  QUEST) are redirected to the Switch text. Both sides are found by the SHA-1 of the text (nothing is stored), each exactly once in its file;
  otherwise the build stops.
- **R-11** The order flags of the skill-effect descriptions are cleared (the Japanese gives the turns first, the translations the amount) only
  when Android-only texts were written, and only if each flag holds the expected value.
