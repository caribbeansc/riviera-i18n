"""Build the Android version of a language pack from the user's own files.

What it needs, all of it the user's::

    * the split APKs of the app (``base.apk``, ``split_*.apk``) in one folder        -> Project.apk_dir
    * the Switch dump of the same game (``exefs/main``, ``romfs/data*.bin``)        -> Project.exefs / Project.romfs
      (the Android app is the Switch game with a touch interface: the English script, the font metrics and the pictures come from there)

What it writes: a folder with the same split APKs, patched and signed with a key of the project (``build/android/<code>``). Nothing of the
user's files is modified. In order:

1. ``libapp.so``: the script of the language (:mod:`.text`) and the proportional-text hooks (:mod:`.hooks`);
2. the picture containers (:mod:`.images`, :mod:`.assets`);
3. ``classes.dex`` and ``resources.arsc`` of ``base.apk``: the app name, the Java strings (optional, :mod:`.javastrings`) and, unless
   ``keep_license_check``, the licence check of the store (:mod:`.licensecheck`);
4. every APK is rebuilt, aligned and signed (:mod:`.apk`).

The library is pinned by its SHA-256: this is the build of version 1.0.4 (versionCode 37) of the app, and any other is refused before
anything is written.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

from .. import builds, font, sge
from .. import images as swimages
from .. import nso as nsomod
from ..config import ConfigError, Project, interpreter
from ..packs import LangPack
from . import apk, arsc, hooks, images, javastrings, licensecheck, text
from .assets import AndroidAssets
from .elf import Elf
from . import AndroidError

LIBRARY = "lib/arm64-v8a/libapp.so"
ATLAS_SOURCE = "data/System/systemTexture3.pck"        # in the Switch's data.bin: the font atlas the Spanish letters are drawn into


class BuildError(AndroidError):
    """The Android build cannot proceed."""


def find_entry(apk_dir: Path, entry: str) -> Path:
    """The split APK of ``apk_dir`` that contains ``entry``."""
    for f in sorted(apk_dir.glob("*.apk")):
        with zipfile.ZipFile(f) as z:
            if entry in z.namelist():
                return f
    raise BuildError(f"none of the APKs in {apk_dir} contains {entry}: the folder must hold all the split APKs of the app "
                     "(base.apk, split_config.arm64_v8a.apk, split_asset_expansion.apk, ...)")


def require_android(project: Project) -> Path:
    if not project.has_android():
        raise ConfigError("No Android app files configured. Put the split APKs of the app in one folder and point the tool at it:\n"
                          f"    {interpreter()} rpl.py setup --apk-dir /path/to/the/apks")
    return Path(project.apk_dir)


def keystore_path(project: Project) -> Path:
    given = os.environ.get("RPL_KEYSTORE") or project.extra.get("keystore")
    return Path(given).expanduser() if given else project.android_work / "riviera.keystore"


def read_library(apk_dir: Path, hooks_data: hooks.Hooks) -> tuple[bytes, Path]:
    split = find_entry(apk_dir, LIBRARY)
    with zipfile.ZipFile(split) as z:
        lib = z.read(LIBRARY)
    got = hashlib.sha256(lib).hexdigest()
    if got != hooks_data.library_sha256:
        raise BuildError(f"{split.name}: this is not the build of the app this toolkit supports (version 1.0.4, versionCode 37).\n"
                         f"    libapp.so SHA-256 is {got[:16]}…, expected {hooks_data.library_sha256[:16]}…")
    return lib, split


def switch_atlas(romfs: Path) -> bytes:
    with sge.Archive(romfs / "data.bin") as arc:
        return arc.read_path(ATLAS_SOURCE)


def build(project: Project, pack: LangPack, *, keep_license_check: bool = False, say=print) -> Path:
    """Build the Android version of ``pack`` and return the folder with the signed APKs."""
    apk_dir = require_android(project)
    exefs, romfs = project.require_switch()
    if not pack.supports("android"):
        raise BuildError(f"the language pack {pack.code!r} has no Android layout (lang.json: platforms.android)")
    work = project.android_work
    work.mkdir(parents=True, exist_ok=True)
    out = project.android_build(pack.code)

    say(f"Android build of {pack.english_name} ({pack.code})")
    hooks_data = hooks.load()
    lib, lib_split = read_library(apk_dir, hooks_data)
    nso = nsomod.Nso(exefs / "main")
    builds.for_nso(nso)                                                   # refuses an executable of another build

    atlas = None
    if pack.needs_font_patch:
        say("  font: drawing the letters of the language into the atlas")
        atlas = font.make_atlas(nso, switch_atlas(romfs))

    say("library:")
    elf = Elf(lib)
    plan = text.plan(elf, nso, pack, font_writes=atlas.writes if atlas else None, say=say)
    seg_off, seg_va = text.apply(elf, plan, say)
    tables, charset = hooks.engine_tables(nso, hooks_data, atlas.writes if atlas else None)
    done = hooks.install(elf, seg_off, seg_va, tables=tables, charset=charset if atlas else None, hooks=hooks_data)
    say(f"  hooks installed: {done['hooks']} caves, {done['replaced']} replaced functions, {done['patches']} patches"
        + (", extended character string" if done["charset"] else ""))

    say("pictures:")
    translated, warnings = swimages.translated_packages(pack.path, romfs / "data_en.bin")
    for w in warnings:
        say(f"  warning: {w}")
    with AndroidAssets(apk_dir, work) as assets:
        donor = images.Donor(romfs, translated)
        try:
            repl = images.build(pack, assets, donor, atlas.pck if atlas else None, say)
            say(f"  rebuilding the containers ({len(repl)} files)")
            containers = assets.pack(repl, work / "containers")
        finally:
            donor.close()
    say("  " + ", ".join(f"{name} {n}" for name, (_, n) in containers.items()) + " files replaced")

    say("code and resources:")
    base_split = apk_dir / "base.apk"
    with zipfile.ZipFile(base_split) as z:
        dexes = {n: z.read(n) for n in z.namelist() if n.startswith("classes") and n.endswith(".dex")}
        resources = z.read("resources.arsc")
    java = javastrings.translate_dex(base_split, javastrings.read_entries(pack.path / "android" / "java.jsonl"), say)
    if java:
        dexes.update(java)
    if keep_license_check:
        say("  store licence check kept: the app will refuse to start once re-signed unless the store signed it")
    else:
        patched = []
        for name in sorted(dexes):
            if licensecheck.find_code_item(dexes[name]) is not None:
                dexes[name] = licensecheck.patch_dex(dexes[name])
                patched.append(name)
        if not patched:
            raise BuildError("the licence client of the store was not found in the code of base.apk (a different version of the app?)")
        say(f"  {', '.join(patched)}: store licence check disabled (only for your own purchased copy; see docs/ANDROID.md)")
    resources = arsc.rename_app(resources)

    say("signing:")
    replacements: dict[str, dict[str, bytes | Path]] = {
        lib_split.name: {LIBRARY: bytes(elf.data)},
        "split_asset_expansion.apk": {f"assets/{name}": path for name, (path, _) in containers.items()},
        "base.apk": {**dexes, "resources.arsc": resources},
    }
    apk.build_apks(apk_dir, out, keystore_path(project), replacements, say)
    say(f"done: {out}")
    return out
