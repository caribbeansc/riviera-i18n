# Riviera: The Promised Land, in your language

**English** · [Español](README.es.md)

[![Download the patcher](https://img.shields.io/badge/Download-patcher%20for%20Windows%20%C2%B7%20macOS-2ea44f?style=for-the-badge&logo=github)](https://github.com/caribbeansc/riviera-i18n/releases/latest)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/caribbeansc)

**Riviera: The Promised Land** (Sting) has no Spanish. The Switch version speaks English, Japanese, Korean and Chinese;
the Android app speaks only Japanese.

**Just want to play?** Grab the ready-to-run patcher for Windows or macOS from the
[**latest release**](https://github.com/caribbeansc/riviera-i18n/releases/latest). No Python, no terminal. See
[Play it](#play-it--the-easy-way-no-python-no-terminal) below.

**What this repository is for:** translating the game without reverse-engineering anything. Point it at your own copy
of the game and it builds you a Spanish version for **Switch** (as a mod for an emulator, or for a console running
Atmosphère) and for **Android** (Spanish, and also English, which the Android app never had). A language is a folder
(`langs/<code>/`), not code.

It ships Spanish, and English for Android:

| Platform | Language | Script | Artwork | State |
|---|---|---:|---:|---|
| Switch v1.0.0 | Español | 11 360 strings (16 723 rows) | 200 pictures | playable, played from chapter 1 in Ryujinx |
| Android v1.0.4 | Español | the same + 121 Android-only strings | 200 + 18 Android-only pictures | built; checked on a phone and in an emulator |
| Android v1.0.4 | English | the Switch's official English + 121 Android-only strings | the Switch's official English pictures + 18 Android-only pictures | built; checked in an emulator |

PC (Steam) is **not covered yet**.

> **You need your own copy of the game.** These tools read the files of your own dump or app. They do not contain the
> game and cannot get it for you. For Android you need **both** the Android app and a Switch dump (the Android app has no
> English; the Switch dump is where the English text and pictures come from).

## What "Spanish" means here: a spanglish translation

On purpose, the menus, the user interface, the labels, the banners and every **name** (characters, enemies, weapons, items,
skills, places, the names of the options) stay in the game's original English. What is in Spanish is the story and everything
that *explains* something:

- dialogue, narration and the options you pick inside a dialogue,
- descriptions of places, items and battle tips,
- the help lines of the menus, the text of the skill effects, the instructions and the explanation of every option of the
  configuration screen,
- the pictures with text in them that tell the story: the intro, the scene titles, the captions of the CG, the chapter cards
  and the poem.

*Magi* and *Diviner* are made-up words of the game and are not translated. Accents, `ñ`, `¿` and `¡` show in the game: the
font of the game has no `¿` and `¡` and lost its accented letters in this build, so the toolkit draws them into the font.

## Play it — the easy way (no Python, no terminal)

Download the patcher from the [**latest release**](https://github.com/caribbeansc/riviera-i18n/releases/latest). It is built
automatically from this repository and contains nothing from the game. Pick the file for your computer:

- **Windows:** `Riviera-Patcher-Windows.exe`, double-click it. The first time, Windows may warn that it does not recognise the app (it is
  free software without a paid publisher certificate): click **More info**, then **Run anyway**. The whole source is in this repository.
- **macOS:** `Riviera-Patcher-macOS-AppleSilicon.zip` for an M1/M2/M3 Mac or `…-Intel.zip` for an older one (menu → *About This Mac*).
  Unzip it, then **right-click the app → Open** the first time (it is not signed with a paid Apple certificate).

Then, in the **Switch** tab: point it at your own backup (`.xci` / `.nsp`, which needs your own `prod.keys`) or at the exefs and romfs folders
your emulator extracted, pick a language, and click **Set up**, **Build the mod** and **Install in an emulator** (or **ZIP for a console**).
The **Android** tab does the same for the Android app, but it also needs the Android SDK build-tools and a JDK on your computer:
[docs/ANDROID.md](docs/ANDROID.md). What the patcher makes goes to the **`Riviera-i18n`** folder inside your user folder
(`build/`, with the configuration and the unpacked files next to it).

## Play it — from source

You need Python 3.10+ ([python.org](https://www.python.org/downloads/); on Windows tick *Add python.exe to PATH*) and Pillow.

```
git clone https://github.com/caribbeansc/riviera-i18n
cd riviera-i18n
pip install -r requirements.txt
python rpl.py
```

`python rpl.py` opens a menu; each entry is also a command (`python rpl.py <command> --help`). Details for every case,
including where to get your files from, are in [docs/SETUP.md](docs/SETUP.md).

### Switch, in an emulator

1. Have your own dump. Either a backup (`.xci` or `.nsp`, which needs **your own `prod.keys`** and
   [hactool](https://github.com/SciresM/hactool)) or the exefs and the romfs that your emulator extracts
   (*Extract Data → ExeFS* and *RomFS*): no keys needed.
2. Tell the tool where it is, once:
   ```
   python rpl.py setup --xci "Riviera.xci" --keys prod.keys
   # or:  python rpl.py setup --exefs path/to/exefs --romfs path/to/romfs
   ```
3. Build and install:
   ```
   python rpl.py switch build es
   python rpl.py switch install es          # finds Ryujinx, Eden, yuzu and forks on its own
   ```
   Other places: `--to <mods folder>` for any emulator, `--adb` for Eden on an Android device.
4. In the emulator, enable the mod for the game (right-click the game → *Add-ons* / *Open Mod Location*) and set the game's
   language to **English**: the Spanish takes the place of the English.

**On a console** running Atmosphère, `python rpl.py switch package es` writes a ZIP to unpack at the root of the SD card.
It has not been tried on a real console yet.

### Android

The patched app is re-signed with a key made on your machine, so the original (signed by Google Play) has to be uninstalled
first, which removes its local saves. Read [docs/ANDROID.md](docs/ANDROID.md) before you start: it says what you need, how to
get the APKs out of your phone, how to move your saves, and what the build changes inside the app.

```
python rpl.py setup --apk-dir path/to/the/apks
python rpl.py android build es            # or: en
python rpl.py android install es
```

One thing the build does that you should know about: the original app carries Google Play's licence check, and a re-signed copy fails it
and closes at start-up. So, unless you pass `--keep-license-check`, the build switches that check off **in the copy it is patching**. It is meant
for an app you bought, patched on your machine for your phone; [docs/ANDROID.md](docs/ANDROID.md) explains what exactly changes.

### Your saves

The save format is the same on Switch, Android and PC, so you can carry a game from one to the other:
[docs/SAVES.md](docs/SAVES.md).

## About the translations

The Spanish was written by an LLM (Claude), in batches, from the game's official English, with a glossary. It went through automatic checks
(markers, segments, characters, whether every line fits its box with the real glyph widths, and the macOS spell checker) and a
sampled review of 600 random strings by other LLM reviewers, which found four small problems that were fixed. It has been
played from the start of chapter 1 onwards, but **it has not been proofread line by line and the whole game has not been played
through with it**. Take it as a good starting point and help polish it: fixing a line takes a minute and every correction reaches
everyone; see [Fix a line, or add a language](#fix-a-line-or-add-a-language).

## Fix a line, or add a language

```
python rpl.py extract es          # work/switch/lang/es/units.jsonl: the English of your dump next to the Spanish
# edit the "t" lists in that file
python rpl.py validate es         # markers, segments, characters, and whether it fits the boxes
python rpl.py sync es             # work/ -> langs/es/text.jsonl, keys and translations only
python rpl.py switch build es
```

A new language: `python rpl.py newlang fr --name "Français" --like es`. Then commit `langs/<code>/` and open a pull request.
Small ones land soonest. The rules for the text, and what a language needs, are in
[docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md) and, for Spanish, [langs/es/GLOSSARY.md](langs/es/GLOSSARY.md).

## No game data, by design

A translation is stored as a reference to a string plus your text, never the original:

```json
{"k": "a9993e364706816a", "t": ["Pulsa el botón B1"]}
```

`k` is a fingerprint (the first 16 hex digits of the SHA-1 of the string as the game stores it): enough to find the string in
your copy, useless for reconstructing it. The artwork is either text that this project draws itself on an empty canvas, or the
pixels the translation changes over a picture only you have. A test scans every pack for Japanese, Korean, Chinese and
full-width characters and fails if it finds any; `rpl.py sync` refuses to write one.

On your own machine there are no limits: `extract` shows you the game's text next to your translation, and `unpack` opens the
containers. That all lives in `work/`, which is never shared.

## For developers

How the game stores its text, fonts and pictures, the traps, and what each part of the toolkit does:
[docs/PIPELINE.md](docs/PIPELINE.md). The behaviour that matters is written down as numbered requirements in
[docs/specs/](docs/specs/), and the tests name the requirement they cover.

```
pip install -r requirements-dev.txt
pytest -m "not game"     # no game files needed (synthetic dumps)
pytest                   # + the tests that need your own dump (python rpl.py setup first)
```

With the Switch v1.0.0 dump, the patch for the executable is byte for byte the one that was played (a test pins its checksum); the pictures are
the same too, give or take a few anti-aliased pixels of one font glyph depending on your Pillow version.

## Questions

**Will it break my save?** It changes text and pictures, not game logic. Back up your saves anyway. On Android, installing the
patched app means uninstalling the original, which removes its saves: [docs/ANDROID.md](docs/ANDROID.md) explains how to keep them.

**Which emulators?** The Switch mod was tried on Ryujinx. The installer also knows the mod folders of Ryubing, Astris, yuzu, sudachi,
Eden, Citron and Suyu, which read mods the same way, on Windows, Mac and Linux. Anything else: `switch install es --to <the mods folder>`.
Eden on Android: `--adb`.

**Which versions of the game?** Switch v1.0.0 and Android v1.0.4. The tool recognises the build of your files and says so
when it is not one it knows: the addresses it patches are fixed per build.

**Can I go back?** On Switch, delete the mod folder (or switch it off in *Add-ons*): nothing of the game is changed. On Android,
reinstall the original from Google Play.

**Was AI involved?** Yes, in the translation and in the code, and it is written down rather than glossed over: see
[About the translations](#about-the-translations).

## Support

If this made the game playable for you, you can buy me a coffee. Fixing a line that reads wrong helps just as much.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/caribbeansc)

## Sister projects

The same approach (a toolkit plus language packs that never hold the game's own text) drives
[medarot-rb-i18n](https://github.com/caribbeansc/medarot-rb-i18n), [medarot9-i18n](https://github.com/caribbeansc/medarot9-i18n)
and [mdr-navi-i18n](https://github.com/caribbeansc/mdr-navi-i18n).

## Credits

What this project stands on, in detail in [NOTICE](NOTICE) and [docs/EXTERNAL-REPOS.md](docs/EXTERNAL-REPOS.md):

- [SciresM/hactool](https://github.com/SciresM/hactool): opens a Switch backup (`.xci` / `.nsp`) to get at the executable and
  the romfs.
- [python-pillow/Pillow](https://github.com/python-pillow/Pillow): every picture the toolkit reads, draws or composites.
- [Ryujinx](https://ryujinx.app/) and [Eden](https://eden-emu.dev/): where the Switch mod was tried.
- The Android SDK's `apksigner` and `zipalign`, and optionally [apktool](https://apktool.org/): re-signing and patching the app.

## Licence

Code MIT ([LICENSE](LICENSE)); translations CC BY-SA 4.0 ([LICENSE-TRANSLATIONS](LICENSE-TRANSLATIONS)). Unofficial fan project,
not affiliated with Sting Entertainment, Nintendo or Google ([NOTICE](NOTICE)). Please do not open issues or pull requests
containing game files or the original text of the game.
