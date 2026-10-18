"""Project paths, user configuration and emulator detection.

Nothing here touches the game: it only decides *where* things are. Your dumps are
never copied into the project; every step reads them in place (the only exception is
an XCI/NSP backup, which has to be unpacked once into ``work/``).
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .builds import TITLE_ID

CONFIG_NAME = "rpl.config.json"
GAME_NAME = "Riviera: The Promised Land"

#: Files that say "this folder is a dump of the game".
ROMFS_FILES = ("data.bin", "data_en.bin")


class ConfigError(Exception):
    """Raised when the project cannot be located or a dump is unusable."""


def repo_root() -> Path:
    """The checkout this module lives in (or the unpacked bundle of a frozen app)."""
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    """Where configuration, ``work/`` and ``build/`` live: ``RPL_HOME``, the checkout, or a folder in your home for a frozen app."""
    override = os.environ.get("RPL_HOME")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return Path.home() / "Riviera-i18n"
    return repo_root()


def looks_like_romfs(path) -> bool:
    """True if ``path`` is the romfs of this game."""
    if not path:
        return False
    path = Path(path)
    return all((path / f).is_file() for f in ROMFS_FILES)


def looks_like_exefs(path) -> bool:
    """True if ``path`` is the exefs of this game (it has ``main``, an NSO)."""
    if not path:
        return False
    main = Path(path) / "main"
    try:
        with open(main, "rb") as f:
            return f.read(4) == b"NSO0"
    except OSError:
        return False


@dataclass
class Project:
    root: Path
    work: Path
    build: Path
    langs: Path
    exefs: Path | None = None
    romfs: Path | None = None
    xci: Path | None = None            # a backup the exefs/romfs were (or will be) unpacked from
    keys: Path | None = None           # your own prod.keys, to open the backup
    apk_dir: Path | None = None        # the folder with the split APKs of the Android app
    title_id: str = TITLE_ID
    extra: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- paths --
    @property
    def config_file(self) -> Path:
        return self.root / CONFIG_NAME

    @property
    def switch_work(self) -> Path:
        """Working area for the Switch dump (unpacked backups, caches)."""
        return self.work / "switch"

    @property
    def android_work(self) -> Path:
        return self.work / "android"

    def switch_build(self, code: str) -> Path:
        return self.build / "switch" / code

    def android_build(self, code: str) -> Path:
        return self.build / "android" / code

    def lang_dir(self, code: str) -> Path:
        return self.langs / code

    # --------------------------------------------------------------- dumps ---
    def has_switch(self) -> bool:
        return looks_like_exefs(self.exefs) and looks_like_romfs(self.romfs)

    def require_switch(self) -> tuple[Path, Path]:
        if not self.has_switch():
            raise ConfigError(
                "No Switch game files configured. Point the tool at the exefs and romfs of your own dump:\n"
                f"    {interpreter()} rpl.py setup --exefs /path/to/exefs --romfs /path/to/romfs\n"
                "or at a backup (needs your own prod.keys):\n"
                f"    {interpreter()} rpl.py setup --xci /path/to/game.xci --keys /path/to/prod.keys")
        return Path(self.exefs), Path(self.romfs)

    def has_android(self) -> bool:
        return bool(self.apk_dir) and (Path(self.apk_dir) / "base.apk").is_file()

    # ------------------------------------------------------------- config ---
    def save(self) -> None:
        data = {"exefs": str(self.exefs) if self.exefs else None,
                "romfs": str(self.romfs) if self.romfs else None,
                "xci": str(self.xci) if self.xci else None,
                "keys": str(self.keys) if self.keys else None,
                "apk_dir": str(self.apk_dir) if self.apk_dir else None}
        data.update(self.extra)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def set_switch(self, exefs, romfs) -> None:
        exefs, romfs = Path(exefs).expanduser().resolve(), Path(romfs).expanduser().resolve()
        if not looks_like_exefs(exefs):
            raise ConfigError(f"{exefs} does not look like this game's exefs: expected a file called 'main' (an NSO) inside it.")
        if not looks_like_romfs(romfs):
            raise ConfigError(f"{romfs} does not look like this game's romfs: expected {' and '.join(ROMFS_FILES)} inside it.")
        self.exefs, self.romfs = exefs, romfs
        self.save()

    def set_android(self, apk_dir) -> None:
        apk_dir = Path(apk_dir).expanduser().resolve()
        if not (apk_dir / "base.apk").is_file():
            raise ConfigError(f"{apk_dir} has no base.apk: put the split APKs of the app (base.apk, split_*.apk) in one folder.")
        self.apk_dir = apk_dir
        self.save()


def _path(value) -> Path | None:
    return Path(value).expanduser() if value else None


def load(root: Path | None = None) -> Project:
    """Load the project. Precedence: environment (``RPL_EXEFS``, ``RPL_ROMFS``, ``RPL_APK_DIR``), then the stored config,
    then the usual places (``game/exefs`` and ``game/romfs`` next to the checkout). ``RPL_HOME`` moves the config, ``work/`` and
    ``build/``; ``RPL_LANGS`` points at another folder of language packs."""
    root = Path(root) if root else user_dir()
    stored: dict = {}
    config_file = root / CONFIG_NAME
    if config_file.exists():
        try:
            stored = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
    known = {"exefs", "romfs", "xci", "keys", "apk_dir"}
    exefs = _path(os.environ.get("RPL_EXEFS")) or _path(stored.get("exefs"))
    romfs = _path(os.environ.get("RPL_ROMFS")) or _path(stored.get("romfs"))
    if not looks_like_exefs(exefs):
        exefs = next((c for c in (root / "game" / "exefs", root / "exefs") if looks_like_exefs(c)), None)
    if not looks_like_romfs(romfs):
        romfs = next((c for c in (root / "game" / "romfs", root / "romfs") if looks_like_romfs(c)), None)
    langs = _path(os.environ.get("RPL_LANGS")) or repo_root() / "langs"
    return Project(root=root, work=root / "work", build=root / "build", langs=langs,
                   exefs=exefs, romfs=romfs, xci=_path(stored.get("xci")), keys=_path(stored.get("keys")),
                   apk_dir=_path(os.environ.get("RPL_APK_DIR")) or _path(stored.get("apk_dir")),
                   extra={k: v for k, v in stored.items() if k not in known})


# ------------------------------------------------------------- emulators ----

@dataclass
class ModTarget:
    """A directory where an emulator looks for mods."""
    emulator: str
    path: Path        # <…>/<title id>/ : the mod goes in a subdirectory of this
    style: str        # "ryujinx" | "yuzu"


def _appdata() -> Path | None:
    value = os.environ.get("APPDATA")
    return Path(value) if value else None


def _emulator_roots() -> list[tuple[str, Path, str]]:
    """``(emulator, directory holding per-title mod dirs, style)`` candidates."""
    system = platform.system()
    home = Path.home()
    out: list[tuple[str, Path, str]] = []

    # Ryujinx and its forks: <data>/mods/contents/<lowercase title id>/<Mod>/{exefs,romfs}
    ryujinx_names = ["Ryujinx", "Ryubing"]
    # yuzu family: <data>/load/<UPPERCASE TITLE ID>/<Mod>/{exefs,romfs}
    yuzu_names = ["yuzu", "sudachi", "eden", "citron", "suyu"]

    if system == "Windows":
        appdata = _appdata()
        if appdata:
            for name in ryujinx_names:
                out.append((name, appdata / name / "mods" / "contents", "ryujinx"))
            for name in yuzu_names:
                out.append((name, appdata / name / "load", "yuzu"))
    elif system == "Darwin":
        support = home / "Library" / "Application Support"
        for name in ryujinx_names:
            out.append((name, support / name / "mods" / "contents", "ryujinx"))
        # Astris ships Ryujinx inside an app container.
        out.append((
            "Astris",
            home / "Library" / "Containers" / "V380-Ori.Astris" / "Data" / "Library"
            / "Application Support" / "Ryujinx" / "mods" / "contents",
            "ryujinx",
        ))
        for name in yuzu_names:
            out.append((name, support / name / "load", "yuzu"))
    else:  # Linux and the rest
        config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        share = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        for name in ryujinx_names:
            out.append((name, config / name / "mods" / "contents", "ryujinx"))
            out.append((name, share / name / "mods" / "contents", "ryujinx"))
        for name in yuzu_names:
            out.append((name, share / name / "load", "yuzu"))
            out.append((name, config / name / "load", "yuzu"))
        flatpak = home / ".var" / "app"                       # Flatpak installs
        out.append(("Ryujinx (flatpak)",
                    flatpak / "org.ryujinx.Ryujinx" / "config" / "Ryujinx" / "mods" / "contents", "ryujinx"))

    return out


def detect_mod_targets(title_id: str = TITLE_ID) -> list[ModTarget]:
    """Emulator mod directories that exist on this machine."""
    found: list[ModTarget] = []
    seen: set[Path] = set()
    for emulator, root, style in _emulator_roots():
        if not root.exists():
            continue
        title = title_id.lower() if style == "ryujinx" else title_id.upper()
        target = root / title
        if target in seen:
            continue
        seen.add(target)
        found.append(ModTarget(emulator=emulator, path=target, style=style))
    return found


def python_hint() -> str:
    """How the user should invoke Python, for messages."""
    return "py" if platform.system() == "Windows" else "python3"


def interpreter() -> str:
    return python_hint()
