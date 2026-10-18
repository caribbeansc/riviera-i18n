"""The picture containers of the Android app and the split APK that holds them.

The app keeps its artwork in four containers, ``assets/data.bin`` to ``data4.bin``, inside ``split_asset_expansion.apk`` (the other
files of that APK are the sound). ``data2``, ``data3`` and ``data4`` are updates of ``data``: they use the same paths, and for a path
that several of them hold the **latest** one is the one the game loads. The containers use the same format as the Switch's
(:mod:`riviera.sge`).

The containers are unpacked once into the working area (about 115 MB); nothing is changed in the user's APKs.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .. import sge
from . import AndroidError

ASSET_APK = "split_asset_expansion.apk"
CONTAINERS = ("data.bin", "data2.bin", "data3.bin", "data4.bin")       # in order: later ones override earlier ones
ENTRY = "assets/{}"


class AssetError(AndroidError):
    """The asset APK is missing or is not what this build expects."""


class AndroidAssets:
    """Read access to the four containers of the app, found in the folder with the user's split APKs."""

    def __init__(self, apk_dir, work_dir):
        self.apk = Path(apk_dir) / ASSET_APK
        if not self.apk.is_file():
            raise AssetError(f"{self.apk} not found: put all the split APKs of the app in one folder (base.apk, split_*.apk)")
        self.dir = Path(work_dir) / "assets"
        self.dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.apk) as z:
            for name in CONTAINERS:
                try:
                    info = z.getinfo(ENTRY.format(name))
                except KeyError:
                    raise AssetError(f"{self.apk.name} has no {ENTRY.format(name)}: is this the app's expansion APK?") from None
                dst = self.dir / name
                if not dst.is_file() or dst.stat().st_size != info.file_size:
                    with z.open(info) as src, open(dst, "wb") as out:
                        while chunk := src.read(1 << 20):
                            out.write(chunk)
        self._archives: dict[str, sge.Archive] = {}
        self._where: dict[str, dict[str, tuple]] = {}
        for name in CONTAINERS:
            arc = sge.Archive(self.dir / name)
            self._archives[name] = arc
            self._where[name] = {p: (n, info, value) for p, n, info, value in arc.walk()}

    def close(self) -> None:
        for arc in self._archives.values():
            arc.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def container_file(self, name: str) -> Path:
        return self.dir / name

    def paths(self) -> set[str]:
        out: set[str] = set()
        for where in self._where.values():
            out |= where.keys()
        return out

    def containers_with(self, path: str) -> list[str]:
        """The containers that hold ``path``, oldest first."""
        return [n for n in CONTAINERS if path in self._where[n]]

    def has(self, path: str) -> bool:
        return any(path in w for w in self._where.values())

    def read(self, path: str) -> bytes | None:
        """The bytes the game loads for ``path`` (the latest container that has it), or ``None``."""
        for name in reversed(CONTAINERS):
            hit = self._where[name].get(path)
            if hit:
                return self._archives[name].read(*hit)
        return None

    def pack(self, replacements: dict[str, bytes], out_dir) -> dict[str, tuple[Path, int]]:
        """Rebuild every container with the files of ``replacements`` (``{path: bytes}``) in the folder ``out_dir``. A path is replaced in
        every container that holds it. Returns ``{container: (new file, files replaced)}``."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for name in CONTAINERS:
            dst = out_dir / name
            n = sge.pack(self.dir / name, replacements, dst)
            result[name] = (dst, n)
        return result
