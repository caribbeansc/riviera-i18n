"""Put a built mod where an emulator, or a console running Atmosphère, will load it.

Both emulator families read the same thing: a folder per mod with an ``exefs`` (the IPS patch) and a ``romfs`` (replacement
files), under a folder named after the title id. They differ in where that is and how the title id is written:

========================  ========================================================
Ryujinx and forks         ``<data>/mods/contents/<lowercase title id>/<mod>/``
yuzu, Eden and forks      ``<data>/load/<UPPERCASE TITLE ID>/<mod>/``
Atmosphère (a console)    ``atmosphere/contents/<TITLE ID>/romfs/`` and
                          ``atmosphere/exefs_patches/<mod>/<first 16 bytes of the build id>.ips``
========================  ========================================================

The mod is never merged into the game: removing the folder (or switching it off in the emulator's *Add-ons*) gives you the
original back.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

from ..builds import TITLE_ID

EDEN_ANDROID_PACKAGE = "dev.eden.eden_emulator"


class InstallError(Exception):
    """The mod cannot be installed where you asked."""


def _check_built(built: Path) -> list[Path]:
    ips = sorted((built / "exefs").glob("*.ips"))
    if not ips or not (built / "romfs" / "data.bin").is_file() or not (built / "romfs" / "data_en.bin").is_file():
        raise InstallError(f"{built} is not a built mod: run `python rpl.py switch build <language>` first")
    return ips


def install_to_dir(built: Path, mod_dir: Path) -> Path:
    """Copy the built mod into ``mod_dir`` (a folder that becomes ``<mod>/{exefs,romfs}``), replacing an earlier copy."""
    built, mod_dir = Path(built), Path(mod_dir)
    ips = _check_built(built)
    shutil.rmtree(mod_dir, ignore_errors=True)
    (mod_dir / "exefs").mkdir(parents=True)
    (mod_dir / "romfs").mkdir(parents=True)
    for f in ips:
        shutil.copy2(f, mod_dir / "exefs" / f.name)
    for name in ("data.bin", "data_en.bin"):
        shutil.copy2(built / "romfs" / name, mod_dir / "romfs" / name)
    return mod_dir


def install_to_target(built: Path, target, mod_name: str) -> Path:
    """Install into one of :func:`riviera.config.detect_mod_targets`."""
    return install_to_dir(built, Path(target.path) / mod_name)


def remove_from_dir(mod_dir: Path) -> bool:
    mod_dir = Path(mod_dir)
    if mod_dir.is_dir():
        shutil.rmtree(mod_dir)
        return True
    return False


def package_atmosphere(built: Path, mod_name: str, out_zip: Path) -> Path:
    """A ZIP to unpack at the root of the SD card of a console running Atmosphère."""
    built, out_zip = Path(built), Path(out_zip)
    ips = _check_built(built)
    # Atmosphère names the patch after the first 16 bytes of the build id (32 hex digits)
    patch = next((f for f in ips if len(f.stem) == 32), ips[0])
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_STORED) as z:
        z.write(patch, f"atmosphere/exefs_patches/{mod_name}/{patch.name}")
        for name in ("data.bin", "data_en.bin"):
            z.write(built / "romfs" / name, f"atmosphere/contents/{TITLE_ID}/romfs/{name}")
    return out_zip


def _adb(adb: str, serial: str | None, *args: str) -> str:
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    done = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if done.returncode != 0:
        raise InstallError(f"adb {' '.join(args[:2])} failed: {(done.stderr or done.stdout).strip()[-200:]}")
    return done.stdout


def install_android_emulator(built: Path, mod_name: str, *, serial: str | None = None, package: str = EDEN_ANDROID_PACKAGE,
                             adb: str | None = None, say=print) -> str:
    """Push the mod to Eden (or another yuzu fork) running on an Android device, over adb. Close the emulator first."""
    ips = _check_built(Path(built))
    adb = adb or shutil.which("adb")
    if not adb:
        raise InstallError("adb not found: install the Android platform-tools or put adb on your PATH")
    if _adb(adb, serial, "shell", "pidof", package).strip():
        raise InstallError(f"{package} is running: close it before installing (the files would be in use)")
    target = f"/sdcard/Android/data/{package}/files/load/{TITLE_ID}/{mod_name}"
    _adb(adb, serial, "shell", f"rm -rf '{target}'; mkdir -p '{target}/exefs' '{target}/romfs'")
    for f in ips:
        say(f"push {f.name}")
        _adb(adb, serial, "push", str(f), f"{target}/exefs/")
    for name in ("data.bin", "data_en.bin"):
        say(f"push {name}")
        _adb(adb, serial, "push", str(Path(built) / "romfs" / name), f"{target}/romfs/")
    return target
