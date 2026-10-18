# External projects this repository stands on

This project is a thin layer over a handful of other people's work. This file records what each one gives us, how it reaches the
user, and under which licence, so the credit in the README has somewhere to point and anyone auditing the build can see what goes
into it.

Nothing here bundles any part of the game. These are tools and libraries that read *your own* copy on *your own* machine; see
[NOTICE](../NOTICE).

## Needed to build

- **[Pillow](https://github.com/python-pillow/Pillow)**: the Pillow team, HPND (MIT-style). Reads and writes every picture (WebP with
  alpha, PNG), composites the translated-picture deltas and draws the accented letters of the font.

## Needed only to open a backup

- **[hactool](https://github.com/SciresM/hactool)**: SciresM, ISC. Decrypts and extracts the executable and the romfs from a Switch
  backup (`.xci` / `.nsp`). It needs **your own `prod.keys`**, which this project never contains. Not needed if your emulator already
  extracted the exefs and the romfs.

## Needed only for Android

- **Android SDK build-tools** (`apksigner`, `zipalign`): Google, Apache-2.0. Re-sign and align the patched app.
- **JDK** (`keytool`, and `java` for `apksigner`): makes the key that signs the patched app on your machine.
- **[apktool](https://apktool.org/)**: iBotPeaches, Apache-2.0. Optional: only to translate the few strings the app keeps in Java.
- **[adb](https://developer.android.com/tools/adb)** (platform-tools): Google, Apache-2.0. Installs the app on a device.
  See [ANDROID.md](ANDROID.md).

## Used to develop and test, not part of the build

- **[Ryujinx](https://ryujinx.app/)** (MIT) and **[Eden](https://eden-emu.dev/)** (GPL-3.0): where the Switch mod was tried.
- **[Ghidra](https://ghidra-sre.org/)** (Apache-2.0): reading the executables.
- **LLVM / clang** (Apache-2.0 with LLVM exception): building the small hook library for the Android app.

## Sibling projects

- **[medarot-rb-i18n](https://github.com/caribbeansc/medarot-rb-i18n)**, **[medarot9-i18n](https://github.com/caribbeansc/medarot9-i18n)**,
  **[mdr-navi-i18n](https://github.com/caribbeansc/mdr-navi-i18n)**: fan-translation toolkits with the same shape: language packs that
  hold a key plus a fingerprint of the source string and the translation, never the game's own text. The layout of this repository,
  its licences and its specs follow theirs.
