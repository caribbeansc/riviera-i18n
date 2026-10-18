# The Android version

The Android app is the Switch game with a touch interface, and it speaks only Japanese. The build patches **your own copy of the
app** with the script and the pictures of a language pack, and signs the result with a key of your own. Spanish and English are
supported (English is new: the Android app never had it). Version 1.0.4 (version code 37) of the app is the one the toolkit knows;
a different one is refused.

```
python rpl.py setup --apk-dir path/to/the/apks
python rpl.py android build es            # or: en
python rpl.py android install es          # the phone or the emulator that adb sees
```

## What you need

| | Why |
|---|---|
| The split APKs of the app (`base.apk`, `split_config.arm64_v8a.apk`, `split_asset_expansion.apk`, ...) | The app to patch. They are only read. |
| A Switch dump of the same game (`exefs/main`, `romfs/data.bin`, `romfs/data_en.bin`) | The Android app has no English. The English script, the metrics of the font and most pictures come from there. See [SETUP.md](SETUP.md). |
| Python 3.10+ and Pillow | The toolkit (`pip install -r requirements.txt`). |
| The Android SDK **build-tools** (`zipalign`, `apksigner`) and a **JDK** (`keytool`; `apksigner` runs on Java) | Align and sign the patched app. They are looked up in `ANDROID_HOME` (or `ANDROID_SDK_ROOT`) and then on the `PATH`; a missing one is reported by name. |
| `adb` (platform-tools) | `android install`. You can also install the APKs another way. |
| *Optional:* [apktool](https://apktool.org/) (and Java) | Translates the few messages that live in the app's Java code. Without it the app is built all the same and the exit dialog and the cloud-backup messages stay in Japanese. Put `apktool` on the `PATH` or set `APKTOOL_JAR`. |

Only the arm64 build of the app is covered (every phone of the last years).

### Getting the APKs out of your phone

With the phone connected and USB debugging on:

```
adb shell pm path jp.co.sting.riviera          # lists base.apk and the split_*.apk with their paths
mkdir apks
adb pull <each path printed above> apks/       # one adb pull per line
```

## Build

`python rpl.py android build <code>` takes about a minute and writes `build/android/<code>/` (the same split APKs, patched and signed;
about 625 MB, most of it the sound that is copied as it is). It never writes in your APK folder or in your dump. The working area
`work/android/` keeps what is worth keeping between builds: the picture containers unpacked from the app (about 115 MB), the rebuilt ones
and the signing key.

What it does, in order:

1. **`libapp.so`** (the game's code): the script of the language replaces the Japanese one, slot by slot; the proportional-text hooks
   are installed ([SPEC-014](specs/SPEC-014-android-text.md), [SPEC-015](specs/SPEC-015-android-hooks.md)).
2. **The picture containers** (`data*.bin`, in `split_asset_expansion.apk`): the Switch pictures (English, or the translated ones)
   replace the Android ones, the labels of the screens only Android has are put in, and the LOOK sprites are drawn
   ([SPEC-016](specs/SPEC-016-android-artwork.md)).
3. **`classes.dex` and `resources.arsc`** of `base.apk`: the licence check (below), the Java strings (optional) and the name of the app.
4. **Every APK** is rebuilt without its old signature, aligned and signed with the same key ([SPEC-013](specs/SPEC-013-android-build.md)).

### Your own key, and updating

The app is re-signed with a key created on your machine (`work/android/riviera.keystore`, or the file in `RPL_KEYSTORE`). Keep it: a new
build signed with the same key **updates the installed app and keeps its saves**; one signed with another key has to be uninstalled first.

### What changes in the language you pick

The text in `langs/<code>/android/text.jsonl` is only what exists in the Android app and not in the Switch (the touch tutorials, the team-editing
help, the skill-effect descriptions with numbers, the zone names, the cloud-backup messages) plus, for a translated language, the
`langs/<code>/text.jsonl` script shared with the Switch. Where the Android text is the official English the pack holds a reference to the
string of your Switch dump instead of the text itself (SPEC-014/R-9): the repository carries no line of the game's script.

## Install and your saves

```
python rpl.py android install es            # adb install-multiple -r --user 0 on every APK of the build
python rpl.py android install es --serial emulator-5554     # if several devices are connected
```

**The first time**, the original app (signed by Google Play) must be uninstalled, and Android deletes its data with it. The app keeps its
saves in private storage that you cannot read without root, so there is **no ordinary way to rescue them**: the app's own cloud backup does
not help either, because the sign-in it uses fails for a re-signed app. If you want to keep progress, either have a rooted phone (copy
`/data/data/jp.co.sting.riviera/files/savedata/` before you uninstall, and put it back afterwards; [SAVES.md](SAVES.md) explains the
conversion and the permissions), or start from a save made in a Switch emulator and convert it ([SAVES.md](SAVES.md)), which also needs a
way to write in that folder. After that first installation, updates with the same key keep the saves.

`--user 0` is the main user of the phone: the profile of a work space or a private space is not touched.

## The licence check of your own copy (optional)

The app carries Google's licence client (PairIP). At start-up it asks the Play service whether the installed copy is licensed; a copy
signed with another key is told no, the licence screen opens and the app closes. The translation cannot work without getting past that check,
so the build disables it **in the copy it is patching**: one method, `LicenseClient.initializeLicenseCheck()`, is replaced by a `return-void`
(nothing is downloaded, nothing of Google's or of anyone's account is touched). It is for an app **you bought**, patched on **your** machine
for **your** phone; it is not a way to run a game you did not pay for, and it is not offered as one. `--keep-license-check` leaves the check as it is
(the app then closes at start-up once it is re-signed). [SPEC-012](specs/SPEC-012-license-check.md) has the details.

## For people who make languages

* Add `"android": {}` (or `{"soft": 1.12}`) under `platforms` in `lang.json`; without it the pack does not build for Android.
* `langs/<code>/android/text.jsonl` and `java.jsonl`: the Android-only strings, keyed by the fingerprint of their Japanese (the same trick
  as the main script: [SPEC-005](specs/SPEC-005-translation-keys.md)). The format and its rules are in [SPEC-014](specs/SPEC-014-android-text.md).
* `langs/<code>/android/images/manifest.json`: the pictures of the screens only Android has (the options screen, the cloud-backup screen, the
  voice-language buttons, ...), as `full`, `delta` and `layer` entries ([SPEC-016](specs/SPEC-016-android-artwork.md)). They are drawn with
  `python tools/android/render_images.py --lang <code> --apk-dir <apks>` (a development tool: it uses the fonts of the machine it runs on and
  stores the result in the pack, so players do not need those fonts).

## How the hooks were made (for auditing)

`riviera/android/data/hooks.bin` is the code that gives the Android text engine the proportional widths of the Switch's: C compiled
once with LLVM 18 (`tools/android/hooks.c`, `tools/android/build_hooks.py`). It has **no game data**: the tables of font metrics and the
character string are empty holes the build fills from your Switch executable, and the instruction each hook displaces is a `nop` slot filled
from your library; `hooks.json` keeps only a fingerprint of `address + instruction` per site, so a library that is not 1.0.4 is refused before
anything is written. To check that the shipped files come from the sources:

```
python tools/android/build_hooks.py --lib path/to/the/original/libapp.so --llvm-bin path/to/llvm/bin --check
```

(LLVM 18: `clang`, `ld.lld`, `llvm-objcopy` and `llvm-nm`; the shipped files were made with 18.1.8. `--llvm-bin` or the `LLVM_BIN`
variable say where they are; without them they are looked up on the `PATH`.)

## What has been checked, and what has not

Spanish and English were built from the same code, installed on a phone (Spanish) and in an Android emulator (both) and played from the start of
chapter 1: title, options, save lists, exploration (MOVE and LOOK), dialogues, encounters, item selection and the start of the first battle.
**Not yet seen on screen:** the touch tutorials that only a new game shows, the team-editing help, the panel of skill effects with numbers,
the names of the zones and the cloud-backup screens (the app needs a Google sign-in that a re-signed copy cannot do).
