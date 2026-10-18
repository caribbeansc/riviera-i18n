"""Command line: ``python rpl.py`` opens a menu, ``python rpl.py <command> --help`` explains each command.

    setup      point the tool at your own copy of the game
    doctor     check the tools, your dumps and the language packs
    langs      list the language packs
    switch     build / install / package the Switch mod
    android    build / install the patched Android app
    saves      check and convert saves between Switch, Android and PC
    unpack     unpack a data container into work/ (for translators)
    extract    list the strings of your dump next to the translations (for translators)
    newlang    start a new language from the key list of an existing one
    sync       move your edits from work/ into langs/ (keys and translations only)
    validate   check a language pack against the rules and, with your dump, against the game's boxes
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
from pathlib import Path

from . import __version__, config, packs, sge, ui
from .config import ConfigError, Project

EXIT_USAGE = 2

#: Errors of the platform modules that mean "tell the user and stop": the command line shows their message without a traceback.
#: They are matched by the names in the class hierarchy so that this module does not have to import the Android code to know them.
DOMAIN_ERRORS = {"BuildError", "ExtractError", "InstallError", "ImageError", "UnknownBuild", "AndroidError", "SaveError"}


class CommandError(Exception):
    """A problem to report to the user without a traceback."""


# ------------------------------------------------------------------ helpers --

def _pack(project: Project, code: str | None, platform_name: str) -> packs.LangPack:
    available = [p for p in packs.discover(project.langs) if p.supports(platform_name)]
    if not available:
        raise CommandError(f"no language pack supports {platform_name}")
    if code is None:
        if len(available) == 1:
            return available[0]
        code = ui.choose([p.code for p in available], "Language")
    pack = packs.get_pack(project.langs, code)
    if not pack.supports(platform_name):
        raise CommandError(f"the {code} pack does not cover {platform_name} "
                           f"(it covers: {', '.join(k for k in pack.meta.get('platforms', {})) or 'nothing'})")
    return pack


def _tool(name: str) -> str | None:
    return shutil.which(name)


# -------------------------------------------------------------------- setup --

def cmd_setup(args, project: Project) -> int:
    changed = False
    if args.xci:
        from .switch import extract
        ui.step("Unpacking the backup")
        exefs, romfs = extract.unpack(args.xci, project.switch_work, keys=args.keys, hactool=args.hactool, say=ui.info)
        project.xci = Path(args.xci).expanduser().resolve()
        project.keys = Path(args.keys).expanduser().resolve() if args.keys else project.keys
        project.set_switch(exefs, romfs)
        changed = True
    elif args.exefs or args.romfs:
        if not (args.exefs and args.romfs):
            raise CommandError("give both --exefs and --romfs")
        project.set_switch(args.exefs, args.romfs)
        changed = True
    if args.apk_dir:
        project.set_android(args.apk_dir)
        changed = True
    if changed:
        ui.ok(f"saved to {project.config_file}")
    return cmd_doctor(args, project)


# ------------------------------------------------------------------- doctor --

def cmd_doctor(args, project: Project) -> int:
    ui.banner("Riviera: The Promised Land, in your language", f"rpl {__version__}")
    problems = 0

    ui.heading("Python and tools")
    ui.kv("Python", platform.python_version(), status="ok" if sys.version_info >= (3, 10) else "fail")
    try:
        import PIL
        ui.kv("Pillow", PIL.__version__, status="ok")
    except ImportError:
        ui.kv("Pillow", "missing: pip install -r requirements.txt", status="fail")
        problems += 1
    from .switch import extract
    hactool = extract.find_hactool()
    keys = extract.find_keys(project.keys)
    ui.kv("hactool", str(hactool) if hactool else "not found (only needed to open a .xci / .nsp)", status="ok" if hactool else "warn")
    ui.kv("prod.keys", str(keys) if keys else "not found (only needed to open a .xci / .nsp)", status="ok" if keys else "warn")
    for tool, why in (("adb", "to install onto a device"), ("java", "Android only"), ("keytool", "Android only"),
                      ("apksigner", "Android only"), ("zipalign", "Android only"), ("apktool", "optional, Android only")):
        found = _tool(tool)
        ui.kv(tool, found or f"not found ({why})", status="ok" if found else "warn")

    ui.heading("Language packs")
    try:
        found = packs.discover(project.langs)
    except packs.PackError as e:
        ui.fail(str(e))
        found, problems = [], problems + 1
    for p in found:
        covers = ", ".join(p.meta.get("platforms", {})) or "-"
        ui.kv(p.code, f"{p.name}  [{covers}]  {len(p.text())} strings", status="ok")
    leaks = packs.source_text_problems(project.langs)
    ui.kv("source text", "none found in langs/" if not leaks else f"{len(leaks)} files look like game text", status="ok" if not leaks else "fail")
    for line in leaks[:5]:
        ui.detail(line)
    problems += bool(leaks)

    ui.heading("Switch dump")
    if project.has_switch():
        from .nso import Nso
        from . import builds
        try:
            nso = Nso(project.exefs / "main")
            b = builds.for_nso(nso)
            ui.kv("exefs", f"{project.exefs}", status="ok")
            ui.kv("build", f"{b.version} ({b.build_id[:16]}…)", status="ok")
        except (builds.UnknownBuild, ValueError) as e:
            ui.kv("exefs", str(e), status="fail")
            problems += 1
        ui.kv("romfs", f"{project.romfs}", status="ok")
    else:
        ui.kv("dump", "not set: python rpl.py setup --xci GAME.xci   (or --exefs DIR --romfs DIR)", status="warn")

    ui.heading("Android app")
    if project.has_android():
        ui.kv("apk folder", str(project.apk_dir), status="ok")
        for f in sorted(Path(project.apk_dir).glob("*.apk")):
            ui.detail(f"{f.name}  {f.stat().st_size // 1024} KB")
    else:
        ui.kv("apk folder", "not set: python rpl.py setup --apk-dir DIR  (the folder with base.apk and the split_*.apk)", status="warn")
    return 1 if problems else 0


def cmd_langs(args, project: Project) -> int:
    rows = []
    for p in packs.discover(project.langs):
        rows.append((p.code, p.name, ", ".join(p.meta.get("platforms", {})), p.meta.get("scope", ""), len(p.text())))
    ui.table(rows, headers=("code", "name", "platforms", "scope", "strings"))
    return 0


# ------------------------------------------------------------------- switch --

def cmd_switch(args, project: Project) -> int:
    from .switch import build as sw_build, install as sw_install

    action = args.action
    if action == "build":
        pack = _pack(project, args.lang, "switch")
        ui.step(f"Building the Switch mod: {pack.name}")
        try:
            report = sw_build.build(project, pack, out_dir=args.out, soft=args.soft, with_romfs=not args.no_romfs, say=ui.info)
        except (sw_build.BuildError, ConfigError) as e:
            raise CommandError(str(e)) from None
        s = report.summary
        ui.kv("rows", f"{s['rows_translated']} translated ({s['in_place']} in place, {s['relocated']} moved)", status="ok")
        ui.kv("overflow", f"{s['overflow']} rows do not fit their box", status="ok" if not s["overflow"] else "warn")
        ui.kv("verification", f"{s['verification_failures']} failures", status="ok" if not s["verification_failures"] else "fail")
        if s.get("missing_glyphs"):
            ui.kv("no glyph", "".join(s["missing_glyphs"]), status="warn")
        for w in report.warnings[:5]:
            ui.warn(w)
        ui.ok(f"mod written to {report.out_dir}")
        return 0 if report.ok else 1

    pack = _pack(project, args.lang, "switch")
    built = Path(args.built) if args.built else project.switch_build(pack.code)
    try:
        if action == "install":
            if args.adb:
                target = sw_install.install_android_emulator(built, pack.mod_name, serial=args.serial, package=args.package, say=ui.info)
                ui.ok(f"installed on the device: {target}")
                return 0
            if args.to:
                dest = sw_install.install_to_dir(built, Path(args.to) / pack.mod_name)
                ui.ok(f"installed in {dest}")
                return 0
            targets = config.detect_mod_targets()
            if not targets:
                raise CommandError("no emulator found. Use --to <the mods folder of your emulator> (e.g. its load/ folder), "
                                   "--adb for Eden on an Android device, or `switch package` for a console.")
            for t in targets:
                dest = sw_install.install_to_target(built, t, pack.mod_name)
                ui.ok(f"{t.emulator}: {dest}")
            ui.info("Enable the mod in the emulator (right-click the game → Open Mod Location / Add-ons) and set the game's language to English.")
            return 0
        if action == "remove":
            for t in config.detect_mod_targets():
                if sw_install.remove_from_dir(Path(t.path) / pack.mod_name):
                    ui.ok(f"removed from {t.emulator}")
            return 0
        if action == "package":
            out = Path(args.zip) if args.zip else project.build / f"{pack.mod_name}-switch-atmosphere.zip"
            sw_install.package_atmosphere(built, pack.mod_name, out)
            ui.ok(f"unpack {out} at the root of the SD card")
            return 0
    except sw_install.InstallError as e:
        raise CommandError(str(e)) from None
    return EXIT_USAGE


# ------------------------------------------------------------------ android --

def cmd_android(args, project: Project) -> int:
    try:
        from .android import build as and_build, install as and_install
    except ImportError as e:
        raise CommandError(f"the Android part is not available in this checkout ({e})") from None
    pack = _pack(project, args.lang, "android")
    if args.action == "build":
        ui.step(f"Building the Android app: {pack.name}")
        out = and_build.build(project, pack, keep_license_check=args.keep_license_check, say=ui.info)
        ui.ok(f"APKs written to {out}")
        return 0
    out = Path(args.built) if args.built else project.android_build(pack.code)
    and_install.install(out, serial=args.serial)
    return 0


def cmd_saves(args, project: Project) -> int:
    from . import saves
    return saves.main(args.rest)


# ------------------------------------------------------------ translators ---

def cmd_unpack(args, project: Project) -> int:
    exefs, romfs = project.require_switch()
    src = romfs / args.container
    dest = project.switch_work / Path(args.container).stem
    ui.step(f"Unpacking {src.name}")
    n = sge.extract(str(src), str(dest))
    ui.ok(f"{n} files in {dest}")
    return 0


def cmd_extract(args, project: Project) -> int:
    from . import workflow
    return workflow.extract(project, args.like, args.lang, ui)


def cmd_newlang(args, project: Project) -> int:
    from . import workflow
    return workflow.newlang(project, args.code, args.name, args.like, ui)


def cmd_sync(args, project: Project) -> int:
    from . import workflow
    return workflow.sync(project, args.lang, ui)


def cmd_validate(args, project: Project) -> int:
    from . import workflow
    return workflow.validate(project, args.lang, ui)


# ------------------------------------------------------------------ parser ---

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rpl", description="Riviera: The Promised Land, in your language.")
    ap.add_argument("--version", action="version", version=f"rpl {__version__}")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("setup", help="point the tool at your own copy of the game")
    p.add_argument("--xci", help="a Switch backup (.xci / .nsp): it is unpacked into work/")
    p.add_argument("--keys", help="your own prod.keys, to open the backup")
    p.add_argument("--hactool", help="path to hactool")
    p.add_argument("--exefs", help="folder with the exefs of your dump (it has 'main')")
    p.add_argument("--romfs", help="folder with the romfs of your dump (data.bin, data_en.bin)")
    p.add_argument("--apk-dir", help="folder with base.apk and the split_*.apk of the Android app")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor", help="check the tools, your dumps and the language packs")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("langs", help="list the language packs")
    p.set_defaults(func=cmd_langs)

    p = sub.add_parser("switch", help="the Switch mod")
    p.add_argument("action", choices=["build", "install", "remove", "package"])
    p.add_argument("lang", nargs="?", help="language code (es)")
    p.add_argument("--out", help="build: where to write the mod (default build/switch/<lang>)")
    p.add_argument("--built", help="install / package: a built mod folder (default build/switch/<lang>)")
    p.add_argument("--soft", type=float, help="build: how far dialogue lines may widen (the pack's value by default)")
    p.add_argument("--no-romfs", action="store_true", help="build: only the executable patch")
    p.add_argument("--to", help="install: a mods folder (Ryujinx: mods/contents/<title id>, yuzu/Eden: load/<TITLE ID>)")
    p.add_argument("--adb", action="store_true", help="install: Eden on an Android device, over adb")
    p.add_argument("--serial", help="install --adb: the device serial")
    p.add_argument("--package", default="dev.eden.eden_emulator", help="install --adb: the emulator's package name")
    p.add_argument("--zip", help="package: where to write the Atmosphère ZIP")
    p.set_defaults(func=cmd_switch)

    p = sub.add_parser("android", help="the patched Android app")
    p.add_argument("action", choices=["build", "install"])
    p.add_argument("lang", nargs="?", help="language code (es, en)")
    p.add_argument("--built", help="install: a folder with the built APKs (default build/android/<lang>)")
    p.add_argument("--serial", help="install: the device serial")
    p.add_argument("--keep-license-check", action="store_true",
                   help="build: do not disable the Google Play licence check (a re-signed app will not start)")
    p.set_defaults(func=cmd_android)

    p = sub.add_parser("saves", help="check and convert saves between Switch, Android and PC", add_help=False)
    p.add_argument("rest", nargs=argparse.REMAINDER, help="dump | verify | switch2android | android2switch | switch2switch (see docs/SAVES.md)")
    p.set_defaults(func=cmd_saves)

    p = sub.add_parser("unpack", help="unpack a data container of your Switch dump into work/")
    p.add_argument("container", nargs="?", default="data_en.bin")
    p.set_defaults(func=cmd_unpack)

    p = sub.add_parser("extract", help="write the strings of your dump, with the translations of a language, into work/")
    p.add_argument("lang", nargs="?", help="the language whose translations to show next to them")
    p.add_argument("--like", default="es", help="the pack whose key list says what is in scope (default es)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("newlang", help="start a new language from the key list of another")
    p.add_argument("code")
    p.add_argument("--name", required=True, help="the language's own name (Français)")
    p.add_argument("--like", default="es")
    p.set_defaults(func=cmd_newlang)

    p = sub.add_parser("sync", help="move your edits from work/ into langs/")
    p.add_argument("lang")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("validate", help="check a language pack")
    p.add_argument("lang")
    p.set_defaults(func=cmd_validate)
    return ap


# -------------------------------------------------------------------- menu ---

def _menu_setup(project: Project) -> None:
    src = ui.choose(["a Switch backup (.xci / .nsp)", "an exefs and a romfs folder", "the Android APK folder"], "What have you got")
    ns = argparse.Namespace(xci=None, keys=None, hactool=None, exefs=None, romfs=None, apk_dir=None)
    if src.startswith("a Switch"):
        ns.xci = ui.ask("Path to the backup")
        ns.keys = ui.ask("Path to your prod.keys (empty = look for it)") or None
    elif src.startswith("an exefs"):
        ns.exefs, ns.romfs = ui.ask("Path to the exefs folder"), ui.ask("Path to the romfs folder")
    else:
        ns.apk_dir = ui.ask("Path to the folder with base.apk")
    cmd_setup(ns, project)


def _menu_switch(project: Project, action: str) -> None:
    cmd_switch(argparse.Namespace(action=action, lang=None, out=None, built=None, soft=None, no_romfs=False, to=None, adb=False,
                                  serial=None, package="dev.eden.eden_emulator", zip=None), project)


def _menu_android(project: Project, action: str) -> None:
    cmd_android(argparse.Namespace(action=action, lang=None, built=None, serial=None, keep_license_check=False), project)


def menu(project: Project) -> int:
    ui.banner("Riviera: The Promised Land, in your language", f"rpl {__version__}")
    options = [
        ("1", "Point me at the game", "set up your dumps"),
        ("2", "Build the Switch mod", ""),
        ("3", "Install it in an emulator", ""),
        ("4", "Package it for a console", "Atmosphère ZIP"),
        ("5", "Build the Android app", ""),
        ("6", "Install it on a device", "adb"),
        ("7", "Diagnose", "tools, dumps, packs"),
    ]
    actions = {
        "1": lambda: _menu_setup(project),
        "2": lambda: _menu_switch(project, "build"),
        "3": lambda: _menu_switch(project, "install"),
        "4": lambda: _menu_switch(project, "package"),
        "5": lambda: _menu_android(project, "build"),
        "6": lambda: _menu_android(project, "install"),
        "7": lambda: cmd_doctor(argparse.Namespace(), project),
    }
    while True:
        try:
            key = ui.menu(options, "Choose")
            if key == "0":
                return 0
            try:
                actions[key]()
            except (CommandError, ConfigError, packs.PackError) as e:
                ui.fail(str(e))
            ui.pause()
        except ui.Aborted:
            return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "saves":                                  # the converter has its own parser (options such as --help included)
        return cmd_saves(argparse.Namespace(rest=argv[1:]), None)
    args = build_parser().parse_args(argv)
    project = config.load()
    try:
        if not args.command:
            return menu(project)
        return args.func(args, project)
    except (CommandError, ConfigError, packs.PackError) as e:
        ui.fail(str(e))
        return 1
    except ui.Aborted:
        return 130
    except KeyError as e:
        ui.fail(f"missing: {e}")
        return 1
    except Exception as e:                                           # known domain errors from the platform modules
        if {c.__name__ for c in type(e).__mro__} & DOMAIN_ERRORS:
            ui.fail(str(e))
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
