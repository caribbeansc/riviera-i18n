# SPEC-008: Translation validator and workflow

A translation is a list of segments with exactly the segments of the original, the same markers and none of the characters the engine
cannot take. **Errors** break the game or the line composer; **warnings** are judgement calls.

## Requirements

- **R-1** A translation that follows the rules has no errors and no warnings.
- **R-2** The number of segments must match the original's, and a segment cannot be empty or not text.
- **R-3** Markers must survive: `p1` slots, `%d` formats, `{}` slots, `[names]`, `B1` button icons, `R(12)`, and the symbols the font draws.
- **R-4** A silence (a segment that is only ellipsis or punctuation) is copied as it is.
- **R-5** `;`, `|`, tabs and line breaks are errors: the composer breaks the lines.
- **R-6** Japanese, Korean, Chinese and full-width characters are errors, except the ones the original segment itself has.
- **R-7** Warnings: much longer than the original, a question or exclamation with no `¿` / `¡`, extra spaces.
- **R-8** A pack may forbid patterns (`validation.forbidden`): each match is an error with the pack's message.
- **R-9** A character that is neither ASCII nor in `validation.extra_chars` is reported.
- **R-10** `extract` lists the distinct strings of the dump with their fingerprint, their readable segments and their tags, and writes
  those in the scope of a reference pack next to a language's translation, under `work/`.
- **R-11** `newlang` creates a pack from another's metadata with an empty script; `sync` moves the translations of `work/` into
  `langs/`, refusing a wrong number of segments.
- **R-12** `validate` fails on a lost marker, and with a dump it also checks that everything fits its box.
- **R-13** `validate` rejects characters the pack does not allow (those the game's English uses are fine) and applies the pack's
  forbidden patterns.
