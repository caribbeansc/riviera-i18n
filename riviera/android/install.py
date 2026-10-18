"""Install the patched split APKs on a phone or an emulator with ``adb``.

``adb install-multiple -r --user 0`` installs the whole set over the previous version and keeps the app's data (the saves), provided it was
signed with the same key; one signed with another key has to be uninstalled first (which erases its saves: back them up). ``--user 0`` is the
main user of the device: other users (a work profile, a private space) are not touched.
"""

from __future__ import annotations

from pathlib import Path

from . import apk


def adb_path() -> str:
    return apk.find_tool("adb", "platform-tools")


def devices(adb: str | None = None) -> list[tuple[str, str]]:
    """``[(serial, state)]`` of the devices ``adb`` sees."""
    out = apk.run([adb or adb_path(), "devices"])
    rows = [line.split() for line in out.splitlines()[1:] if line.strip()]
    return [(r[0], r[1]) for r in rows if len(r) >= 2]


def install(out_dir, serial: str | None = None, say=print) -> list[Path]:
    """Install every APK of ``out_dir``. With several devices connected, ``serial`` says which one."""
    apks = sorted(Path(out_dir).glob("*.apk"))
    if not apks:
        raise apk.ToolError(f"{out_dir} has no APK: build first (python rpl.py android build <language>)")
    adb = adb_path()
    ready = [s for s, state in devices(adb) if state == "device"]
    if not ready:
        raise apk.ToolError("no device is connected (or it has not authorized this computer): check `adb devices`")
    if serial is None and len(ready) > 1:
        raise apk.ToolError("several devices are connected, say which one with a serial: " + ", ".join(ready))
    cmd = [adb] + (["-s", serial] if serial else []) + ["install-multiple", "-r", "--user", "0", *map(str, apks)]
    say(f"installing {len(apks)} APKs" + (f" on {serial}" if serial else ""))
    out = apk.clean(apk.run(cmd))
    say("\n".join(ln for ln in out.splitlines() if ln.strip() in ("Success",) or "Failure" in ln) or out[-200:])
    return apks
