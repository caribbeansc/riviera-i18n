# Setup

You need three things: Python, this repository, and the game files from **your own** copy. About fifteen minutes, most of it
waiting.

## 1. Python 3.10 or newer

| Platform | How |
|---|---|
| Windows | [python.org](https://www.python.org/downloads/): tick *Add python.exe to PATH* |
| macOS | `brew install python` (or python.org) |
| Linux | `sudo apt install python3 python3-pip python3-venv` (or your package manager) |

Check it:

```
python --version        # Windows
python3 --version       # macOS / Linux
```

## 2. This repository and its dependency

```
git clone https://github.com/caribbeansc/riviera-i18n
cd riviera-i18n

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt
```

The virtual environment is optional but keeps things tidy. The only dependency is Pillow.

## 3. The Switch game files

The tools need two things from **your own** dump: the **exefs** (the folder with the executable, `main`) and two files of the
**romfs**, `data.bin` and `data_en.bin`. Version 1.0.0 is the one the toolkit knows. Pick whichever route you already have.

### From an emulator (easiest, no keys)

Ryujinx-family and yuzu-family emulators can do this from the game list:

1. Right-click the game → **Extract Data** (Ryujinx) / **Dump ExeFS** and **Dump RomFS** (yuzu family).
2. Choose an empty folder for each.

### From a backup (`.xci` or `.nsp`)

Needs **your own `prod.keys`** (dump them from your console with Lockpick_RCM; the tool looks in `~/.switch` and in the key folders of
your emulators) and [hactool](https://github.com/SciresM/hactool) (on your PATH, in `tools/bin/`, or `RPL_HACTOOL=path`). Compressed
backups (`.xcz`, `.nsz`) have to be decompressed first, for example with the `nsz` tool.

```
python rpl.py setup --xci "Riviera.xci" --keys prod.keys
```

This unpacks the backup into `work/switch/` once (about 140 MB are kept; the sound banks are dropped).

### What "good" looks like

```
exefs/
└── main                 ← the executable; also rtld, sdk, subsdk*, main.npdm if your emulator wrote them
romfs/
├── data.bin             ← about 80 MB
└── data_en.bin          ← about 33 MB
```

## 4. Point the tool at it

```
python rpl.py setup --exefs /path/to/exefs --romfs /path/to/romfs
python rpl.py doctor
```

`doctor` tells you what it found and what is missing, including which build of the game you have. From here on, just run:

```
python rpl.py
```

## 5. The Android app (only for Android)

You need two things: the split APKs of the app installed on **your own** phone, and the Switch dump above (the Android app has no
English, so the English text and pictures come from the Switch). With the phone connected by USB, with USB debugging on:

```
adb shell pm path jp.co.sting.riviera          # lists base.apk and the split_*.apk with their paths
mkdir apks
adb pull <each path printed above> apks/       # one adb pull per line
python rpl.py setup --apk-dir apks
```

The toolkit knows version 1.0.4 of the app (version code 37). [ANDROID.md](ANDROID.md) has the rest: what else the build needs
(the Android SDK build-tools and a JDK), how it signs the app, and what to do about your saves.

## Notes per platform

**Windows.** Use `python rpl.py`, and quote paths with spaces: `python rpl.py setup --exefs "C:\games\riviera exefs" ...`. The menu works
in `cmd.exe`, PowerShell and Windows Terminal.

**macOS.** If `python` is not found, use `python3`.

**Linux.** Flatpak emulators keep their data under `~/.var/app/...`; `rpl.py switch install` knows Ryujinx's, and `--to <dir>` covers
anything it misses.

## Where things end up

| Path | What | Committed? |
|---|---|---|
| `rpl.config.json` | the paths of your dumps | no |
| `work/` | what is unpacked from your dumps, and the game's text next to the translation (`extract`) | no |
| `build/` | the generated mods and patched apps | no |
| `langs/` | the translations themselves | **yes** |

`work/` is where the game's own text lives on your machine. It is in `.gitignore` and must stay there. `RPL_HOME=<dir>` moves
`rpl.config.json`, `work/` and `build/` somewhere else (handy to keep several dumps apart).
