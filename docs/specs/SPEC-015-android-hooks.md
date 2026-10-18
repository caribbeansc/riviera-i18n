# SPEC-015: Proportional text in the Android library

The Android text engine advances a fixed cell per character, as it does for Japanese; English and the Latin translations need the
per-cell widths the PC and the Switch use. `tools/android/hooks.c` reproduces that on top of the Android functions, plus an adaptive
confirmation box and a scale for dialogue pages that do not fit. It is compiled once (`tools/android/build_hooks.py`, LLVM 18) and
what ships is `riviera/android/data/hooks.bin` + `hooks.json`; the build only installs it.

## Requirements

- **R-1** The blob holds **code only**: the metrics tables and the character string are zero-filled holes in their own section, and the
  instruction each hook displaces is a `nop` slot. `hooks.json` keeps no original instruction, only a short fingerprint of
  `address + word` per site.
- **R-2** The holes are filled from the user's own files: the three metrics tables (rows `x0, width, y offset` of the cells of the Latin
  letters) and the character string come from the Switch executable, with the writes of the font patch applied; a table whose geometry is
  not the one the blob was made for is refused.
- **R-3** Nothing is written unless every site of the library (the hooked instructions, the resume points, the replaced functions, the
  one-instruction patches and, with a character string, the `FNT_init` pair) holds the instruction whose fingerprint `hooks.json` has.
- **R-4** The blob is linked at the start of the appended segment (its address is in `hooks.json`); installing at another address is refused.
- **R-5** Each hook becomes a branch to its cave; each replaced function a branch to its hook; each patch writes its new word; each cave
  gets the instruction it displaced, copied from the user's library.
- **R-6** The extended character string is installed, and `FNT_init` pointed at it, only for languages that need letters the font lacks
  (`needs_font_patch`); otherwise `FNT_init` is left alone and the string area stays empty.
- **R-7** The shipped files are reproducible: `python tools/android/build_hooks.py --lib <original libapp.so> --check` rebuilds them and
  says whether they are the same. (It needs the original library and LLVM, so it is not part of the test suite.)
