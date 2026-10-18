# SPEC-011: The save-game converter

The save format is the same on Switch v1.0.0, Android v1.0.4 and PC v1.0.3. `riviera/saves.py` (`python rpl.py saves ...`) validates the
files, recalculates the checksums, normalises what depends on the platform and rebuilds the rotation table of the autosaves. It uses
only the standard library and contains no game data; see [SAVES.md](../SAVES.md) for how to use it and where the saves live.

```
SYSTEM.DAT   0x1438 bytes   system work, the configuration and the rotation table of the autosaves
AUTOnn.DAT   0x7110 bytes   nn = 00..59
STORYnn.DAT  0x6150 bytes   nn = 00..99
*.PNG        240x136 thumbnail of a save (optional)
each .DAT    u32 sum | header (0x40: magic "2023(C)STING Riviera", version "ver1.0.0", size, type, date) | payload | u32 0 | u32 sum
```

## Requirements

- **R-1** A `.DAT` is `u32 sum | header | payload | u32 0 | u32 sum`. The sum is the byte sum of `[0x44, size - 8)` modulo 2^32 (the header is not covered) and is stored at `+0` and at `size - 4`. The header holds the magic, the version, the size of the file, the type and a date.
- **R-2** Save files are `SYSTEM`, `AUTO00`-`59` and `STORY00`-`99` with `.DAT` or `.PNG`, in any case. Any other file is not a save: it is left alone and listed as ignored.
- **R-3** `verify` rejects what the game rejects (wrong size, magic, version or size in the header; a checksum that matches neither copy; a slot out of range) and only warns about what the game tolerates (the type, copies that differ, padding that is not zero, an implausible date). Either copy of the checksum is enough.
- **R-4** Thumbnails are checked (signature, chunk CRCs, IHDR/IDAT/IEND). A size other than 240x136 and a thumbnail without its `.DAT` are warnings; a `.DAT` without a thumbnail is information.
- **R-5** The input may be the save folder itself, the `<saveId>` folder of Ryujinx (copy `0`, else `1`), any parent of Eden's `<UserID>/<TitleID>` folder (the title folder first, within a bounded depth) or a single file. A path that does not exist is an error.
- **R-6** `dump` only reads. It summarises every slot and the system file, and offers `--json` and `-v` (the fields that hold process addresses). It reports damaged files and still succeeds.
- **R-7** A conversion never modifies its input and always writes a new folder: never the input, inside it or around it. A non-empty output is refused without `--force`, which removes only files that look like saves. Valid thumbnails are copied as they are; a thumbnail whose `.DAT` is not written is dropped.
- **R-8** The message log of every AUTO/STORY is emptied (count 0, entries zeroed) unless `--keep-log`; nothing else in the payload changes.
- **R-9** ConfigWork bit 23 (View Wide, Android only) is cleared when the destination is Switch; for Android it comes from `--dest-system`. `--keep-dest-config` copies the destination's whole ConfigWork and needs `--dest-system`; an invalid `--dest-system` aborts. Otherwise the configuration travels with the save (Controller B included).
- **R-10** The rotation table of `SYSTEM.DAT` is rebuilt from the header dates of the AUTO saves that are written: the newest first, then downwards and wrapping from 0 to 59, the lowest slot winning a tie. `verify` reports a stale table as information. With no AUTO save the table is left as it is.
- **R-11** `--only-newest-auto` and `--no-story` select what is written. A file that does not validate aborts the conversion, or is skipped and reported with `--skip-invalid`.
- **R-12** Both copies of the checksum and the padding are recalculated on output.
- **R-13** The output is verified before anything is written; if it does not validate, nothing is written.
- **R-14** `main(argv)` returns 0 on success, 1 when there are errors or the operation fails (the message goes to stderr, with no traceback) and 2 on a usage error. `verify --strict` fails on warnings too.
- **R-15** The module needs nothing but the standard library, so it runs where Pillow is not installed.
