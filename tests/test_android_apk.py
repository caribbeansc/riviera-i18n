"""Tests of riviera.android.apk and riviera.android.install: rebuilding and signing the split APKs, and finding the SDK tools (SPEC-013).
The external tools are replaced by recorders: nothing here needs the Android SDK."""

import zipfile
from pathlib import Path

import pytest

from riviera.android import apk, install


def make_apk(path, entries, stored=()):
    """A zip with ``entries`` (``{name: bytes}``); the names in ``stored`` are not compressed."""
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED)


def names_and_methods(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: i.compress_type for i in z.infolist()}


def test_rebuild_replaces_entries_drops_signatures_and_keeps_the_method(tmp_path):
    """SPEC-013/R-4: the entries to replace are swapped, the old signature files are dropped and every entry keeps its compression method."""
    src = tmp_path / "a.apk"
    make_apk(src, {"AndroidManifest.xml": b"manifest", "lib/arm64-v8a/libapp.so": b"old", "assets/x.bin": b"x" * 100,
                   "META-INF/CERT.RSA": b"sig", "META-INF/CERT.SF": b"sig", "META-INF/MANIFEST.MF": b"sig", "META-INF/services/keep": b"keep"},
             stored={"lib/arm64-v8a/libapp.so"})
    dst = tmp_path / "b.apk"
    new_file = tmp_path / "x.bin"
    new_file.write_bytes(b"from a file")
    n = apk.rebuild_zip(src, dst, {"lib/arm64-v8a/libapp.so": b"new", "assets/x.bin": new_file})
    assert n == 2
    with zipfile.ZipFile(dst) as z:
        assert z.read("lib/arm64-v8a/libapp.so") == b"new" and z.read("assets/x.bin") == b"from a file"
        assert z.read("AndroidManifest.xml") == b"manifest" and z.read("META-INF/services/keep") == b"keep"
    methods = names_and_methods(dst)
    assert not any(n.startswith("META-INF/") and n.rsplit(".", 1)[-1] in ("SF", "RSA", "EC", "DSA", "MF") for n in methods)
    assert methods["lib/arm64-v8a/libapp.so"] == zipfile.ZIP_STORED and methods["AndroidManifest.xml"] == zipfile.ZIP_DEFLATED


def test_rebuild_refuses_an_entry_the_apk_does_not_have(tmp_path):
    """SPEC-013/R-5: replacing an entry that is not there is an error that names it."""
    src = tmp_path / "a.apk"
    make_apk(src, {"a.txt": b"a"})
    with pytest.raises(apk.ToolError, match="classes.dex"):
        apk.rebuild_zip(src, tmp_path / "b.apk", {"classes.dex": b"x"})


def fake_sdk(tmp_path, versions=("33.0.2", "35.0.0", "34.0.0"), tools=("zipalign", "apksigner")):
    for v in versions:
        d = tmp_path / "sdk" / "build-tools" / v
        d.mkdir(parents=True)
        for t in tools:
            (d / t).write_text("#!/bin/sh\n")
    (tmp_path / "sdk" / "platform-tools").mkdir()
    (tmp_path / "sdk" / "platform-tools" / "adb").write_text("#!/bin/sh\n")
    return tmp_path / "sdk"


def test_tools_come_from_the_newest_build_tools_of_android_home(tmp_path, monkeypatch):
    """SPEC-013/R-7: the SDK tools are looked up in the newest build-tools of ANDROID_HOME, and adb in platform-tools."""
    sdk = fake_sdk(tmp_path)
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    assert apk.find_tool("zipalign").endswith("35.0.0" + __import__("os").sep + "zipalign")
    assert apk.find_tool("adb", "platform-tools").endswith("adb")


def test_a_missing_tool_names_itself_and_the_variable(tmp_path, monkeypatch):
    """SPEC-013/R-7: a tool that is nowhere is an error that names it and the variable to set."""
    monkeypatch.setenv("ANDROID_HOME", str(fake_sdk(tmp_path, tools=("zipalign",))))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setattr(apk.shutil, "which", lambda name: None)
    with pytest.raises(apk.ToolError, match="apksigner.*ANDROID_HOME"):
        apk.find_tool("apksigner")


class Recorder:
    """Stands in for ``apk.run`` and ``apk.find_tool``: remembers the commands and fakes what they would create."""

    def __init__(self, devices=""):
        self.commands = []
        self.devices = devices

    def find_tool(self, name, folder="build-tools"):
        return name

    def run(self, cmd):
        self.commands.append(list(cmd))
        tool = cmd[0]
        if tool == "keytool":
            open(cmd[cmd.index("-keystore") + 1], "wb").write(b"keystore")
        elif tool == "zipalign":
            open(cmd[-1], "wb").write(open(cmd[-2], "rb").read())
        elif tool == "adb" and "devices" in cmd:
            return "List of devices attached\n" + self.devices
        return ""


def test_every_apk_is_rebuilt_and_signed_with_one_key(tmp_path, monkeypatch):
    """SPEC-013/R-4, SPEC-013/R-6: all the APKs of the set are rebuilt and signed with the same key, which is created once; a previous build is cleared."""
    src = tmp_path / "apks"
    src.mkdir()
    make_apk(src / "base.apk", {"classes.dex": b"dex", "resources.arsc": b"arsc"})
    make_apk(src / "split_config.en.apk", {"res/a": b"a"})
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.apk").write_bytes(b"old")
    rec = Recorder()
    monkeypatch.setattr(apk, "run", rec.run)
    monkeypatch.setattr(apk, "find_tool", rec.find_tool)
    ks = tmp_path / "work" / "riviera.keystore"
    written = apk.build_apks(src, out, ks, {"base.apk": {"classes.dex": b"patched"}}, say=lambda *_: None)
    assert [p.name for p in written] == ["base.apk", "split_config.en.apk"] and not (out / "stale.apk").exists()
    assert zipfile.ZipFile(out / "base.apk").read("classes.dex") == b"patched"
    assert zipfile.ZipFile(out / "split_config.en.apk").read("res/a") == b"a"            # not changed, but rebuilt and signed all the same
    tools = [c[0] for c in rec.commands]
    assert tools.count("keytool") == 1 and tools.count("zipalign") == 2 and tools.count("apksigner") == 2
    signers = [c for c in rec.commands if c[0] == "apksigner"]
    assert all(c[c.index("--ks") + 1] == str(ks) for c in signers)                        # the same key for all of them
    apk.build_apks(src, out, ks, {}, say=lambda *_: None)                                   # the second build reuses the key
    assert [c[0] for c in rec.commands].count("keytool") == 1


def test_install_uses_install_multiple_on_the_main_user(tmp_path, monkeypatch):
    """SPEC-013/R-8: adb install-multiple -r --user 0 on every APK of the build."""
    out = tmp_path / "out"
    out.mkdir()
    for n in ("base.apk", "split_a.apk"):
        (out / n).write_bytes(b"x")
    rec = Recorder(devices="emulator-5554\tdevice\n")
    monkeypatch.setattr(apk, "run", rec.run)
    monkeypatch.setattr(apk, "find_tool", rec.find_tool)
    install.install(out, say=lambda *_: None)
    cmd = rec.commands[-1]
    assert cmd[:5] == ["adb", "install-multiple", "-r", "--user", "0"] and [Path(c).name for c in cmd[5:]] == ["base.apk", "split_a.apk"]
    install.install(out, serial="emulator-5554", say=lambda *_: None)
    assert rec.commands[-1][:3] == ["adb", "-s", "emulator-5554"]


def test_install_needs_a_device_and_a_serial_when_there_are_several(tmp_path, monkeypatch):
    """SPEC-013/R-8: it refuses without a ready device, and asks for a serial when several are connected."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "base.apk").write_bytes(b"x")
    monkeypatch.setattr(apk, "find_tool", Recorder().find_tool)
    monkeypatch.setattr(apk, "run", Recorder(devices="abc\tunauthorized\n").run)
    with pytest.raises(apk.ToolError, match="no device"):
        install.install(out, say=lambda *_: None)
    monkeypatch.setattr(apk, "run", Recorder(devices="abc\tdevice\ndef\tdevice\n").run)
    with pytest.raises(apk.ToolError, match="serial.*abc, def"):
        install.install(out, say=lambda *_: None)
    with pytest.raises(apk.ToolError, match="no APK"):
        install.install(tmp_path / "empty", say=lambda *_: None)


def test_tool_output_loses_its_progress_redraws():
    """The output of a failing tool is shown without the progress lines adb redraws with carriage returns."""
    noisy = "Serving...\rss\ress\ress\nFailure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n"
    assert apk.clean(noisy).splitlines()[-1] == "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]"
    assert len(apk.clean("x" * 5000, 100)) <= 101
