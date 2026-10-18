# SPEC-007: Command-line interface

`python rpl.py` opens a numbered menu (no arrow keys, no curses: it behaves the same in `cmd.exe`, over SSH and in a CI log); every
entry is also a command.

## Requirements

- **R-1** `--help` names every command, and `langs` lists the packs with the platforms they cover.
- **R-2** `setup` stores the paths of the dump in `rpl.config.json`, checks that the folders look like the game's, and asks for both
  `--exefs` and `--romfs` together.
- **R-3** `switch build`, `switch install --to` and `switch package --zip` run end to end and leave a mod, an installed copy and a ZIP.
- **R-4** Errors a user can fix (no dump, unknown language, a language that does not cover the platform) are one line that says what to
  do, with exit code 1, and no traceback.
- **R-5** `switch install` without an emulator folder explains the alternatives (`--to`, `--adb`, `switch package`).
- **R-6** `doctor` checks tools, packs and dumps, and fails if a pack contains something that looks like the game's text.
- **R-7** The menu quits on `0` and on Ctrl-C / Ctrl-D.
- **R-8** `saves` hands the rest of its command line to the converter of [SPEC-011](SPEC-011-saves.md) and returns its exit code.
