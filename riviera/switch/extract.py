"""Open a Switch backup (``.xci`` or ``.nsp``) with hactool and keep the two things the build needs.

The build reads ``exefs/main`` and two files of the romfs, ``data.bin`` and ``data_en.bin``. A backup is encrypted, so
unpacking one needs hactool and **your own** ``prod.keys``; neither is part of this repository and the keys are never copied.
If you already have the exefs and romfs extracted by your emulator (*Extract Data → ExeFS / RomFS*), you do not need any of this:
``python rpl.py setup --exefs ... --romfs ...``.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import config
from ..builds import TITLE_ID

KEEP_FROM_ROMFS = ("data.bin", "data_en.bin")           # the romfs is ~1.2 GB; the sound banks are not needed


class ExtractError(Exception):
    """The backup cannot be opened."""


def _exe(name: str) -> str:
    return name + (".exe" if platform.system() == "Windows" else "")


def find_hactool(explicit=None) -> Path | None:
    """hactool: the explicit path, ``RPL_HACTOOL``, ``tools/bin`` next to the checkout, or the PATH."""
    candidates = [explicit, os.environ.get("RPL_HACTOOL"), config.repo_root() / "tools" / "bin" / _exe("hactool")]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    for name in ("hactool", "hactoolnet"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def key_files() -> list[Path]:
    """Places a ``prod.keys`` usually lives: ``~/.switch`` and the key folders of the emulators."""
    home = Path.home()
    out = [home / ".switch" / "prod.keys", home / ".switch" / "keys.txt"]
    for _name, root, style in config._emulator_roots():
        data = root.parent.parent if style == "ryujinx" else root.parent
        out.append(data / ("system" if style == "ryujinx" else "keys") / "prod.keys")
    return out


def find_keys(explicit=None) -> Path | None:
    for c in (explicit, os.environ.get("RPL_KEYS")):
        if c and Path(c).is_file():
            return Path(c)
    return next((k for k in key_files() if k.is_file()), None)


def _run(cmd: list[str]) -> str:
    try:
        done = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace")
    except OSError as e:
        raise ExtractError(f"cannot run {cmd[0]}: {e}") from None
    if done.returncode != 0:
        tail = (done.stderr or done.stdout).strip().splitlines()[-3:]
        raise ExtractError(f"{Path(str(cmd[0])).name} failed: {' | '.join(tail)}")
    return done.stdout


def titlekey_of(tik: Path) -> str | None:
    """The title key of a common ticket (``.tik``), which an eShop ``.nsp`` needs to open its NCAs."""
    data = tik.read_bytes()
    if len(data) < 0x190:
        return None
    return data[0x180:0x190].hex()


def program_nca(hactool: Path, keys: Path, folder: Path, titlekey: str | None = None) -> Path:
    """The NCA of ``folder`` whose content type is Program (the one with the executable and the romfs)."""
    for nca in sorted(folder.glob("*.nca")):
        if nca.name.endswith(".cnmt.nca"):
            continue
        cmd = [hactool, "-k", keys] + ([f"--titlekey={titlekey}"] if titlekey else []) + ["-t", "nca", nca]
        info = _run(cmd)
        if re.search(r"Content Type:\s+Program", info):
            title = re.search(r"Title ID:\s+([0-9a-f]{16})", info)
            if title and title.group(1).upper() != TITLE_ID:
                raise ExtractError(f"this backup is title {title.group(1).upper()}, not {config.GAME_NAME} ({TITLE_ID})")
            return nca
    raise ExtractError("no Program NCA found in the backup: is it a complete dump with its keys?")


def unpack(source, dest, keys=None, hactool=None, say=print) -> tuple[Path, Path]:
    """Unpack ``source`` (.xci / .nsp) into ``dest/exefs`` and ``dest/romfs`` and return both folders.

    Everything the build does not need is dropped, so ``dest`` ends up around 115 MB. A second call with the same, unchanged
    backup returns at once.
    """
    source, dest = Path(source).expanduser(), Path(dest)
    if not source.is_file():
        raise ExtractError(f"{source} does not exist")
    stamp_file = dest / "source.json"
    stamp = {"source": str(source.resolve()), "size": source.stat().st_size, "mtime": int(source.stat().st_mtime)}
    exefs, romfs = dest / "exefs", dest / "romfs"
    if stamp_file.is_file() and json.loads(stamp_file.read_text()) == stamp and config.looks_like_exefs(exefs) and config.looks_like_romfs(romfs):
        say(f"Already unpacked: {dest}")
        return exefs, romfs

    kind = source.suffix.lower()
    if kind in (".xcz", ".nsz"):
        raise ExtractError("compressed backups (.xcz / .nsz) have to be decompressed first, for example with the `nsz` tool")
    if kind not in (".xci", ".nsp"):
        raise ExtractError(f"{source.name}: expected a .xci or a .nsp")
    tool = find_hactool(hactool)
    if not tool:
        raise ExtractError("hactool not found. Put it on your PATH, in tools/bin/, or point RPL_HACTOOL at it "
                           "(https://github.com/SciresM/hactool), or extract the exefs and romfs with your emulator instead.")
    keyfile = find_keys(keys)
    if not keyfile:
        raise ExtractError("prod.keys not found. Dump your own from your console (Lockpick_RCM) and pass --keys, or put it in ~/.switch/.")

    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rpl-", dir=dest) as tmp:
        tmp = Path(tmp)
        containers = tmp / "containers"
        containers.mkdir()
        titlekey = None
        if kind == ".xci":
            say("Opening the cartridge dump")
            _run([tool, "-k", keyfile, "-t", "xci", f"--securedir={containers}", source])
        else:
            say("Opening the eShop package")
            _run([tool, "-k", keyfile, "-t", "pfs0", f"--pfs0dir={containers}", source])
            tik = next(iter(sorted(containers.glob("*.tik"))), None)
            titlekey = titlekey_of(tik) if tik else None
        nca = program_nca(tool, keyfile, containers, titlekey)
        say("Extracting the executable and the romfs (about a minute)")
        shutil.rmtree(exefs, ignore_errors=True)
        shutil.rmtree(romfs, ignore_errors=True)
        full = tmp / "romfs"
        _run([tool, "-k", keyfile] + ([f"--titlekey={titlekey}"] if titlekey else [])
             + ["-t", "nca", f"--exefsdir={exefs}", f"--romfsdir={full}", nca])
        romfs.mkdir(parents=True)
        for name in KEEP_FROM_ROMFS:
            src = full / name
            if not src.is_file():
                raise ExtractError(f"the romfs has no {name}: is this the right game?")
            shutil.move(str(src), romfs / name)
    stamp_file.write_text(json.dumps(stamp, indent=1) + "\n", encoding="utf-8")
    if not (config.looks_like_exefs(exefs) and config.looks_like_romfs(romfs)):
        raise ExtractError("the backup was unpacked but does not look like this game")
    return exefs, romfs
