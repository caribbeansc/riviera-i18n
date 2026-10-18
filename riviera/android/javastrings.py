"""Translate the strings of the app's Java code (an optional step).

A handful of messages live in the Java side of the app, not in the game's script: the "quit the application?" dialog and its buttons,
"Delete file" and the cloud-backup size warning. They are ``const-string`` instructions of ``classes.dex``.

A dex file cannot simply be edited: ART requires its string table sorted by content, and a translation sorts elsewhere than the Japanese it
replaces, which renumbers every reference. So this step lets **apktool** (which needs Java) take the dex apart into smali, replaces the
``const-string`` values there and builds the dex again. It is optional: without apktool the app is built all the same and those few
messages stay in Japanese (they only show when the Back button asks to quit, and in the Google Drive backup).

``langs/<code>/android/java.jsonl`` holds ``{"k": fingerprint of the Japanese text, "t": "translated text"}``.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from ..packs import read_jsonl
from . import AndroidError

CONST = re.compile(r'(const-string(?:/jumbo)? [vp]\d+, )"((?:[^"\\]|\\.)*)"')
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}


class JavaStringsError(AndroidError):
    """The optional step could not run."""


def unescape(literal: str) -> str:
    out, i = [], 0
    while i < len(literal):
        c = literal[i]
        if c == "\\":
            n = literal[i + 1]
            if n == "u":
                out.append(chr(int(literal[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(ESCAPES.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def escape(text: str) -> str:
    out = []
    for ch in text:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ord(ch) > 0x7E:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def translate_smali(src: Path, table: dict[str, str]) -> tuple[int, set[str]]:
    """Replace in the smali tree ``src`` every ``const-string`` whose value has a fingerprint of ``table``. Returns ``(replacements, the
    dex files whose source changed)``: ``smali`` is ``classes.dex``, ``smali_classesN`` is ``classesN.dex``."""
    touched, n = set(), 0
    for path in glob.glob(os.path.join(src, "smali*", "**", "*.smali"), recursive=True):
        text = open(path, encoding="utf-8").read()
        if "\\u" not in text:                                    # only strings with non-ASCII characters can be the Japanese ones
            continue

        def sub(m):
            nonlocal n
            new = table.get(fingerprint(unescape(m.group(2))))
            if new is None:
                return m.group(0)
            n += 1
            top = os.path.relpath(path, src).split(os.sep)[0]
            touched.add("classes.dex" if top == "smali" else top.replace("smali_", "") + ".dex")
            return '%s"%s"' % (m.group(1), escape(new))

        out = CONST.sub(sub, text)
        if out != text:
            open(path, "w", encoding="utf-8").write(out)
    return n, touched


def find_apktool() -> list[str] | None:
    """The command that runs apktool (``APKTOOL_JAR`` with Java, or ``apktool`` on the PATH), or ``None``."""
    jar = os.environ.get("APKTOOL_JAR")
    if jar and Path(jar).is_file() and shutil.which("java"):
        return ["java", "-jar", jar]
    found = shutil.which("apktool")
    return [found] if found else None


def translate_dex(base_apk, entries, say=print) -> dict[str, bytes] | None:
    """The ``classes*.dex`` of ``base_apk`` rebuilt with the strings of ``entries`` (the rows of ``java.jsonl``) translated, as
    ``{entry name: bytes}``; ``None`` if there is nothing to do or apktool is not available (a note is printed)."""
    table = {o["k"]: o["t"] for o in entries}
    if not table:
        return None
    tool = find_apktool()
    if tool is None:
        say("  Java strings: apktool (and Java) not found; the exit dialog and the cloud-backup messages stay in Japanese. "
            "Install apktool or set APKTOOL_JAR to translate them.")
        return None
    work = tempfile.mkdtemp(prefix="riviera_dex_")
    try:
        src, built = os.path.join(work, "src"), os.path.join(work, "out.apk")
        try:
            subprocess.run([*tool, "d", "-f", "-r", str(base_apk), "-o", src], check=True, capture_output=True)
            n, touched = translate_smali(Path(src), table)
            subprocess.run([*tool, "b", src, "-o", built], check=True, capture_output=True)
        except (subprocess.CalledProcessError, OSError) as e:
            detail = getattr(e, "stderr", b"") or b""
            raise JavaStringsError(f"apktool failed: {detail.decode('utf-8', 'replace')[-400:] or e}") from None
        say(f"  Java strings: {n} replaced in {', '.join(sorted(touched)) or 'no dex'} (expected strings: {len(table)})")
        with zipfile.ZipFile(built) as z:                       # only the dex files that changed: the others stay as the app shipped them
            return {name: z.read(name) for name in sorted(touched)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def read_entries(path) -> list[dict]:
    return list(read_jsonl(path)) if Path(path).is_file() else []
