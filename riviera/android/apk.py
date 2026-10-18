"""Put the changed files back into the split APKs, align and sign them.

The app is installed as a set of split APKs (``base.apk`` and ``split_*.apk``). The build copies each of them replacing the entries it
changed (the library, the picture containers, the code and the resources), drops the old signature, aligns the result and signs it with a
key of its own. A signature is mandatory for Android to install anything, and **all the splits must carry the same one**, so every APK of the
set is rebuilt, changed or not.

The key lives in the working area (``work/android/riviera.keystore``) and is created on first use. An app installed with another key (the
one of the store, or of a previous build with another keystore) has to be uninstalled before this one can replace it: keep the keystore to
be able to update in place.

The tools come from the Android SDK: ``zipalign`` and ``apksigner`` (``build-tools``) and ``keytool`` (any JDK). They are looked up under
``ANDROID_HOME`` / ``ANDROID_SDK_ROOT`` and then on the ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import AndroidError

SIGNATURE_SUFFIXES = ("SF", "RSA", "EC", "DSA", "MF")
KEY_ALIAS = "riviera"
KEY_PASSWORD = "riviera"          # the key only signs an app that runs on the user's own device


class ToolError(AndroidError):
    """A tool of the Android SDK is missing or failed."""


def _sdk_roots() -> list[Path]:
    roots = []
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]))
    return roots


def _version_key(p: Path):
    return tuple(int(x) if x.isdigit() else 0 for x in p.name.replace("-", ".").split("."))


def find_tool(name: str, folder: str = "build-tools") -> str:
    """The path of an SDK tool: the newest ``build-tools`` (or ``platform-tools``) of ``ANDROID_HOME``, then the ``PATH``."""
    for root in _sdk_roots():
        base = root / folder
        if folder == "build-tools":
            dirs = sorted((d for d in base.iterdir() if d.is_dir()), key=_version_key, reverse=True) if base.is_dir() else []
        else:
            dirs = [base]
        for d in dirs:
            for suffix in ("", ".bat", ".exe"):
                if (d / (name + suffix)).is_file():
                    return str(d / (name + suffix))
    found = shutil.which(name)
    if found:
        return found
    raise ToolError(f"'{name}' was not found. Install the Android SDK {folder.replace('-', ' ')} (or put {name} on the PATH) "
                    f"and set ANDROID_HOME so that ANDROID_HOME/{folder} exists.")


def clean(output: str, limit: int = 1200) -> str:
    """Tool output without the progress redraws (carriage returns) and cut to its last ``limit`` characters."""
    lines = [ln for part in output.replace("\r", "\n").split("\n") if (ln := part.strip())]
    text = "\n".join(lines)
    return text if len(text) <= limit else "…" + text[-limit:]


def run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    except OSError as e:
        raise ToolError(f"cannot run {cmd[0]}: {e}") from None
    if r.returncode:
        raise ToolError(f"{Path(cmd[0]).name} failed ({r.returncode}):\n{clean(r.stdout + r.stderr)}")
    return r.stdout


def rebuild_zip(src, dst, replace: dict[str, bytes | Path] | None = None) -> int:
    """Copy the archive ``src`` to ``dst`` replacing entries (``{name: bytes or path of a file}``). The signature files are dropped and every
    entry keeps its compression method. Returns how many entries were replaced."""
    replace = replace or {}
    done = 0
    with zipfile.ZipFile(src) as zin:
        missing = set(replace) - {i.filename for i in zin.infolist()}
        if missing:
            raise ToolError(f"{Path(src).name} has no entry {sorted(missing)[0]!r} to replace: is this the right version of the app?")
        with zipfile.ZipFile(dst, "w") as zout:
            for info in zin.infolist():
                if info.filename.startswith("META-INF/") and info.filename.rsplit(".", 1)[-1] in SIGNATURE_SUFFIXES:
                    continue
                new = zipfile.ZipInfo(info.filename, info.date_time)
                new.compress_type = info.compress_type
                new.external_attr = info.external_attr
                with zout.open(new, "w", force_zip64=True) as w:
                    if info.filename in replace:
                        done += 1
                        value = replace[info.filename]
                        if isinstance(value, (bytes, bytearray)):
                            w.write(value)
                        else:
                            with open(value, "rb") as f:
                                shutil.copyfileobj(f, w, 1 << 20)
                    else:
                        with zin.open(info) as r:
                            shutil.copyfileobj(r, w, 1 << 20)
    return done


def ensure_keystore(path) -> Path:
    path = Path(path)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        run([find_tool("keytool"), "-genkeypair", "-keystore", str(path), "-alias", KEY_ALIAS, "-keyalg", "RSA", "-keysize", "2048",
             "-validity", "10000", "-storepass", KEY_PASSWORD, "-keypass", KEY_PASSWORD, "-dname", "CN=riviera-i18n"])
    return path


def align_and_sign(unsigned, dst, keystore) -> None:
    """Align ``unsigned`` (4 bytes, and the uncompressed libraries to a page) into ``dst`` and sign it in place."""
    run([find_tool("zipalign"), "-f", "-p", "4", str(unsigned), str(dst)])
    run([find_tool("apksigner"), "sign", "--ks", str(keystore), "--ks-pass", f"pass:{KEY_PASSWORD}", "--ks-key-alias", KEY_ALIAS, str(dst)])


def build_apks(apk_dir, out_dir, keystore, replacements: dict[str, dict[str, bytes | Path]], say=print) -> list[Path]:
    """Rebuild and sign every APK of ``apk_dir`` into ``out_dir``. ``replacements`` maps an APK file name to its ``{entry: new content}``;
    the other APKs are re-signed unchanged. Returns the written files."""
    apk_dir, out_dir = Path(apk_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in list(out_dir.glob("*.apk")) + list(out_dir.glob("*.idsig")) + list(out_dir.glob("*.tmp")):
        old.unlink()
    keystore = ensure_keystore(keystore)
    written = []
    for src in sorted(apk_dir.glob("*.apk")):
        tmp = out_dir / (src.name + ".tmp")
        n = rebuild_zip(src, tmp, replacements.get(src.name))
        dst = out_dir / src.name
        align_and_sign(tmp, dst, keystore)
        tmp.unlink()
        written.append(dst)
        say(f"  {src.name}: {n} entries replaced, signed")
    return written
