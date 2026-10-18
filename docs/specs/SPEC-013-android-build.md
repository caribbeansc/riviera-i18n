# SPEC-013: The Android build

The Android app is the Switch game with a touch interface, so its script, its font metrics and most of its pictures are the Switch's.
`python rpl.py android build <language>` patches **your own copy** of the app (its split APKs) with the script and the pictures of a
language pack, and writes the result, signed with a key of the project, to `build/android/<code>/`. Nothing in your folders is changed.
How it is used: [ANDROID.md](../ANDROID.md). The parts: the library ([SPEC-014](SPEC-014-android-text.md), [SPEC-015](SPEC-015-android-hooks.md)),
the pictures ([SPEC-016](SPEC-016-android-artwork.md)), the licence check ([SPEC-012](SPEC-012-license-check.md)).

## Requirements

- **R-1** The build needs the folder with the split APKs (`base.apk` and the `split_*.apk`) and the Switch dump of the same game. Without
  either it stops with a message that says how to configure it. It reads those folders and never writes in them.
- **R-2** The library is pinned: `lib/arm64-v8a/libapp.so` of version 1.0.4 (versionCode 37), found in whichever split holds it. A library
  with another SHA-256 is refused before anything is written, and the message says what it found.
- **R-3** A language pack that has no `platforms.android` section in its `lang.json` cannot be built for Android; the error says so.
- **R-4** Every APK of the set is rebuilt, the ones with changes and the ones without (all the splits must carry the same signature): the
  entries to replace are swapped, the old signature files are dropped, every entry keeps its compression method, and the result is
  aligned and signed. The output folder is emptied of the APKs of a previous build first.
- **R-5** A replacement for an entry that the APK does not have is an error that names the entry.
- **R-6** The signing key is created on first use in the working area, or taken from `RPL_KEYSTORE` (or `keystore` in the configuration),
  and reused afterwards, so that a new build can update the installed one.
- **R-7** The SDK tools (`zipalign`, `apksigner`, `keytool`, `adb`) are looked up in the newest `build-tools` (or `platform-tools`) of
  `ANDROID_HOME` / `ANDROID_SDK_ROOT` and then on the `PATH`. A missing tool is an error that names it and the variable to set.
- **R-8** `install` runs `adb install-multiple -r --user 0` on every APK of a build: it refuses if no device is ready and asks for a
  serial if there are several.
- **R-9** The licence step of SPEC-012 is applied to every dex of `base.apk` that holds the client, unless `keep_license_check` is
  set; if no dex holds it the build stops.
- **R-10** The name of the app in `resources.arsc` is replaced by `Riviera`: the old name is found by its SHA-1, the offsets of the
  strings after it and the sizes of the chunks are corrected, and nothing else changes. It works for both string encodings.
