# Saves: carrying your progress to another version

*Riviera: The Promised Land* writes its save files in the **same format** on the Switch, Android and PC versions. `python rpl.py saves`
reads those files, checks them the way the game does when it loads them, and prepares them for another version. Why you might want that:

- you started in an emulator on your computer and want to carry on in the Android version on your phone (or the other way round), or move
  between Ryujinx and Eden;
- you translate the game and want to check a late scene without playing for hours: borrow a save from further on.

The input is **never modified**: a conversion always writes a new folder, and you copy that folder into place yourself. Nothing here
touches the game files, and a save holds your progress, not the game's text.

## The files

| File | What it is |
|---|---|
| `SYSTEM.DAT` | The game's options and what you have obtained, plus the autosave rotation table. |
| `AUTO00.DAT` … `AUTO59.DAT` | The 60 autosave slots (*Auto Save Data* on the title screen). |
| `STORY00.DAT` … `STORY99.DAT` | The manual saves. |
| `AUTOnn.PNG`, `STORYnn.PNG` | The 240×136 thumbnail the slot list shows. Optional: without it the slot has no picture. |

## What it does

| Command | What it does |
|---|---|
| `dump` | Shows what is in a save folder: for every slot its date, area, difficulty, play time, score and party, and the options kept in `SYSTEM.DAT`. |
| `verify` | Runs the checks the game runs on load. Exit code 1 if the game would refuse a file. |
| `switch2android` | Prepares saves made on a Switch (Ryujinx, Eden) for the Android version. |
| `android2switch` | Prepares saves made on Android for a Switch emulator. |
| `switch2switch` | A validated copy between Ryujinx and Eden (same format, same checks). |

Every conversion:

- **empties the message log (LOG)** of each save. The Switch version stores it in a way the Android version cannot read, and opening LOG
  on Android with such a save crashes the game. Playing is not affected; you only lose the log's history. `--keep-log` keeps it.
- **clears the Android-only "View Wide" option** when the destination is a Switch.
- recalculates both checksums and **rebuilds the autosave rotation table** in `SYSTEM.DAT` from the dates of the saves it writes, so the
  files agree with each other (the game recomputes the table when it loads, too).
- **verifies its own output**, with the same code as `verify`, before it writes a single byte.

It does not put anything into your emulator or phone. You do that, after the checks, as described below.

## Where the saves live

| Version | Folder | Notes |
|---|---|---|
| Ryujinx | `<data>/bis/user/save/<saveId>/0` and `…/1` | Two copies: `0` is the committed save and `1` the working copy. Right-click the game → *Open User Save Directory*. |
| Eden (and other yuzu forks) | `<data>/nand/user/save/0000000000000000/<UserID>/01007D6025CB6000/` | Plain files. Right-click the game → *Open Save Data Location*. |
| Eden on an Android phone | `/sdcard/Android/data/dev.eden.eden_emulator/files/nand/user/save/0000000000000000/<UserID>/01007D6025CB6000/` | Same layout. With USB debugging on, `adb pull` and `adb push` can read and write it. |
| Android version | `/data/data/jp.co.sting.riviera/files/savedata/` | The app's **private** storage: see below. |
| PC version | not documented | The format is the same (the code uses the same names and sizes) but nobody has tried it. |

The emulator's `<data>` folder:

| | Ryujinx | Eden |
|---|---|---|
| Windows | `%APPDATA%\Ryujinx` | `%APPDATA%\eden` |
| macOS | `~/Library/Application Support/Ryujinx` | `~/Library/Application Support/eden` |
| Linux | `~/.config/Ryujinx` | `~/.local/share/eden` |

You can give the tool the save folder itself, the `<saveId>` folder of Ryujinx (it reads copy `0`), or any parent of Eden's title folder
(it looks up to six levels down). A single `.DAT` file works for `dump` and `verify` too.

**The Android version's folder is private to the app.** You can only reach it with root, with `run-as` on a build that is debuggable, or on
an emulator image that gives you a root shell. This toolkit does not try to get around that, and this page does not cover how to get any
of those. If you cannot read the folder, you cannot carry saves into or out of the Android app.

## Before you start

1. **Close the emulator or the app.** An emulator rewrites its save when it exits and would undo what you copied.
2. **Back up the destination's current saves**: copy the whole folder somewhere safe.
3. `verify` the source folder.

```
python rpl.py saves verify "<the save folder>"
```

## From Switch to Android

```
python rpl.py saves dump   "<Ryujinx save folder>"
python rpl.py saves verify "<Ryujinx save folder>" --target android
python rpl.py saves switch2android "<Ryujinx save folder>" converted
```

Useful options: `--only-newest-auto` writes just the newest autosave; `--no-story` leaves the manual saves out.

Then, with the Android app stopped:

1. Back up the app's `savedata` folder.
2. Delete the old `AUTO*`, `STORY*` and `SYSTEM.DAT` files there, and copy in everything from `converted/`.
3. The copied files must belong to the app's user and keep the folder's own SELinux context (on a rooted device or an emulator:
   `ls -Z` the folder, then `chown` and `chcon` the files to match; `restorecon` would drop the app-specific part of the context).
4. Start the game, pick **Auto Save Data** on the title screen and choose the slot. The list shows each slot's thumbnail and date.

If the Android app has been used before, copy its `SYSTEM.DAT` out first and keep its settings (see "The configuration travels with the
save" below).

## From Android to Switch

```
python rpl.py saves dump "from_phone"
python rpl.py saves android2switch "from_phone" converted
```

With the emulator closed:

- **Ryujinx:** delete the game's files (`AUTO*`, `STORY*`, `SYSTEM.DAT`) from **both** `<saveId>/0` and `<saveId>/1`, and copy everything
  from `converted/` into both. Leave `ExtraData0`, `ExtraData1` and `saveMeta` alone; do not copy them from another emulator.
- **Eden:** delete the game's files in the title folder and copy everything from `converted/` into it.

Start the game and pick **Auto Save Data**.

## Between Ryujinx and Eden

The two use the same format, so this is a validated copy:

```
python rpl.py saves switch2switch "<Ryujinx save folder>" converted --keep-log
```

`switch2switch` empties the message log like the other two, because they need that. Between Switch emulators you do not, so add
`--keep-log`. Install it as in "From Android to Switch".

## Gotchas

- **The configuration travels with the save.** `SYSTEM.DAT` holds the game's options (voice language, text speed, volumes, the button
  layout...) next to your progress. In particular **Controller B**, which is on by default: with it on, B confirms and **A is "Play Demo"
  on the title screen**. If the title screen starts a demo when you expect it to confirm, that is why. To keep the destination's own
  settings and move only the progress, point at its current `SYSTEM.DAT`:

  ```
  python rpl.py saves android2switch "from_phone" converted --dest-system "<Ryujinx save folder>/0/SYSTEM.DAT" --keep-dest-config
  ```

  Without `--keep-dest-config`, `--dest-system` only keeps the destination's View Wide setting (when the destination is Android).
- **View Wide exists only on Android.** It is cleared for a Switch destination, so the option is harmless if it travels.
- **Replace the whole folder.** The game decides which autosave is the newest from the date inside each file. An old slot left in the
  destination with a later date than yours counts as the newest. Delete the old `AUTO*` and `STORY*` files first.
- **Dates are local time of the device** that wrote the save; moving between devices with different clocks only matters for which slot
  counts as the newest.
- **The folder you write to must be new.** The tool refuses to write into the input, inside it or around it, and refuses a non-empty
  output unless you pass `--force`, which deletes only files that look like saves.
- **A file that does not validate stops the conversion**, with the list of reasons. `--skip-invalid` leaves those files out and reports
  them instead.
- **The in-game cloud backup of the Android version is not a bridge.** It is Android-only and keeps its own container, and on an app that
  has been re-signed the sign-in fails.
- **Manual saves (`STORY*`) and saves made in the middle of a battle have not been tried.** Autosaves have.

## Command reference

```
python rpl.py saves dump <folder|file> [--json] [-v | --verbose]
python rpl.py saves verify <folder> [--target switch|android] [--strict]
python rpl.py saves switch2android <source> <output> [options]
python rpl.py saves android2switch <source> <output> [options]
python rpl.py saves switch2switch  <source> <output> [options]
```

| Option | Applies to | What it does |
|---|---|---|
| `--json` | `dump` | Machine-readable output. |
| `-v`, `--verbose` | `dump` | Also shows the fields that hold process addresses (they tell which platform wrote the save). |
| `--target switch\|android` | `verify` | Also reports what only matters on that platform (for example the View Wide bit on a Switch). |
| `--strict` | `verify` | Exit with 1 on warnings too. |
| `--force` | conversions | Overwrite a non-empty output folder. |
| `--dest-system FILE` | conversions | The destination's current `SYSTEM.DAT`. When the destination is Android, its View Wide setting is kept. |
| `--keep-dest-config` | conversions | With `--dest-system`: keep the destination's whole configuration; only the progress travels. |
| `--only-newest-auto` | conversions | Write only the newest autosave. |
| `--no-story` | conversions | Leave the manual (`STORY*`) saves out. |
| `--skip-invalid` | conversions | Skip files that do not validate instead of stopping. |
| `--keep-log` | conversions | Keep the message log. It can crash the Android version. |

Exit codes: `0` all good; `1` `verify` found errors (or warnings, with `--strict`), or the command failed and printed an `error:` line (a
conversion that fails writes nothing); `2` the command line is wrong.

What `verify` prints:

| Mark | Meaning |
|---|---|
| `E` | The game refuses the file: wrong size, magic, version, size in the header, or a checksum that matches neither copy; or a slot number out of range. |
| `W` | Odd, but the game loads it: a wrong type, two checksums that differ, padding that is not zero, an odd date, a thumbnail of another size or without its `.DAT`. |
| `I` | For your information: a `.DAT` without a thumbnail (the list shows no picture for that slot), a rotation table that the game will rebuild anyway. |

## What has been tested

- Seven real autosaves made in Ryujinx, converted with `switch2android` and loaded in the Android version (v1.0.4) on an emulator: the
  slot list with thumbnails, loading, the menu, Status, exploration, dialogue, an encounter and Item Select. The LOG screen works because
  the log is emptied; with the log left in, opening it crashed the game.
- Real autosaves made in the Android version on an emulator, converted with `android2switch` and loaded in Ryujinx: the slot list with
  thumbnails, loading, Stage Start and the first scene's dialogue.
- Saves read from Eden on an Android phone pass `verify`.

## What has not

- Putting converted saves into **Eden itself**, so `switch2switch` and Eden's folder layout are untested end to end.
- Anything on a **physical phone**: nothing has been written into the Android app of a real device.
- **Manual saves** (`STORY*`; there was no real sample) and saves made **in the middle of a battle**.
- Opening the LOG on a Switch with an Android save converted with `--keep-log`.
- The **PC version**.

If you try one of these, `verify` the result first and keep your backup. A report of what worked is welcome.

## Where the format is written down

The layout of each file, the checksum rule and the offsets are documented at the top of `riviera/saves.py`, and the guarantees the tool
makes are listed in [SPEC-011](specs/SPEC-011-saves.md).
