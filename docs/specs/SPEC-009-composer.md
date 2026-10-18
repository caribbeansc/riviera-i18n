# SPEC-009: The line composer

Spanish text is broken into lines at the **real glyph widths** of the engine, inside boxes deduced from the English, per kind of
row; see [PIPELINE.md](../PIPELINE.md) for the reasons behind each.

## Requirements

- **R-1** `wrap_words` / `wrap_units` split text into the fewest lines that fit the cap; a word wider than the cap gets a line of its
  own; text that fits stays on one line.
- **R-2** The lines are balanced: the cap is tightened to the smallest one that still gives the same number of lines.
- **R-3** Segments follow each other (one chain) when the English of the next starts with a space; a tag opens a new chain.
- **R-4** An interface row whose English has two or more lines is composed in about those lines (`ui_cap`): the widest English line x
  1.25, widened in steps if the Spanish does not fit, and the family cap only if nothing else fits.
- **R-5** Dialogue and lines with a voice clip are composed segment by segment; everything else as a whole row.
- **R-6** A list of `・` bullets keeps one bullet per line.
- **R-7** `compose_row` keeps every marker and puts a break where the English has one (a break between two chained segments goes at the
  start of the second).
- **R-8** A segment that continues the previous one does not end in a comma, because the engine draws the separating comma.
