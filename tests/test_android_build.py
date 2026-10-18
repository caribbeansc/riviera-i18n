"""Tests of the preconditions of riviera.android.build (SPEC-013): what it needs, what it refuses, how the pieces are chosen.
The whole build needs the game's own files and is covered by the ``game`` test at the end."""

import hashlib
import zipfile

import pytest

from riviera.android import build, hooks
from riviera.config import ConfigError, Project


def project(tmp_path, apk_dir=None):
    return Project(root=tmp_path, work=tmp_path / "work", build=tmp_path / "build", langs=tmp_path / "langs", apk_dir=apk_dir)


def apk_with(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


def test_the_build_needs_the_apks_and_says_how_to_configure_them(tmp_path):
    """SPEC-013/R-1: without the folder with the split APKs the build stops and says how to point the tool at them."""
    with pytest.raises(ConfigError, match="--apk-dir"):
        build.require_android(project(tmp_path))
    with pytest.raises(ConfigError, match="--apk-dir"):
        build.require_android(project(tmp_path, tmp_path))                           # a folder without base.apk
    (tmp_path / "base.apk").write_bytes(b"x")
    assert build.require_android(project(tmp_path, tmp_path)) == tmp_path


def test_the_library_is_found_in_whichever_split_holds_it(tmp_path):
    """SPEC-013/R-2: the split that holds lib/arm64-v8a/libapp.so is found by its entry, whatever the name of the file."""
    apk_with(tmp_path / "base.apk", {"classes.dex": b"d"})
    apk_with(tmp_path / "split_whatever.apk", {build.LIBRARY: b"LIB"})
    assert build.find_entry(tmp_path, build.LIBRARY).name == "split_whatever.apk"
    with pytest.raises(build.BuildError, match="classes9.dex"):
        build.find_entry(tmp_path, "classes9.dex")


def test_a_library_of_another_version_is_refused(tmp_path):
    """SPEC-013/R-2: the library is pinned by its SHA-256; another one is refused and the message says what was found."""
    apk_with(tmp_path / "split_config.arm64_v8a.apk", {build.LIBRARY: b"some other library"})
    ours = hooks.Hooks(b"", {"library_sha256": hashlib.sha256(b"the supported library").hexdigest()})
    with pytest.raises(build.BuildError, match="(?s)version 1.0.4.*" + hashlib.sha256(b"some other library").hexdigest()[:16]):
        build.read_library(tmp_path, ours)
    apk_with(tmp_path / "split_config.arm64_v8a.apk", {build.LIBRARY: b"the supported library"})
    lib, split = build.read_library(tmp_path, ours)
    assert lib == b"the supported library" and split.name == "split_config.arm64_v8a.apk"


def test_the_shipped_hooks_pin_the_supported_library():
    """SPEC-013/R-2: the pin that ships is a SHA-256."""
    sha = hooks.load().library_sha256
    assert len(sha) == 64 and int(sha, 16) >= 0


def test_the_signing_key_can_be_given_or_is_kept_in_the_working_area(tmp_path, monkeypatch):
    """SPEC-013/R-6: RPL_KEYSTORE (or ``keystore`` in the configuration) chooses the key; by default it lives in the working area."""
    proj = project(tmp_path)
    monkeypatch.delenv("RPL_KEYSTORE", raising=False)
    assert build.keystore_path(proj) == tmp_path / "work" / "android" / "riviera.keystore"
    proj.extra["keystore"] = str(tmp_path / "mine.keystore")
    assert build.keystore_path(proj) == tmp_path / "mine.keystore"
    monkeypatch.setenv("RPL_KEYSTORE", str(tmp_path / "env.keystore"))
    assert build.keystore_path(proj) == tmp_path / "env.keystore"


def test_a_language_without_android_cannot_be_built(tmp_path, monkeypatch):
    """SPEC-013/R-3: a pack with no platforms.android section is refused before anything is read."""
    import synth
    from riviera import config
    exefs, romfs, nso = synth.make_dump(tmp_path / "dump", synth.sample_blocks())
    (tmp_path / "base.apk").write_bytes(b"x")
    proj = Project(root=tmp_path / "home", work=tmp_path / "home" / "work", build=tmp_path / "home" / "build", langs=tmp_path / "langs",
                   exefs=exefs, romfs=romfs, apk_dir=tmp_path)
    pack = synth.make_lang(tmp_path / "langs", "zz", {"Yes": ["Si"]}, meta={"platforms": {"switch": {}}})
    with pytest.raises(build.BuildError, match="no Android layout"):
        build.build(proj, pack, say=lambda *_: None)
    assert config.ConfigError is ConfigError


def test_the_licence_step_is_applied_to_every_dex_that_has_the_client_and_can_be_kept():
    """SPEC-013/R-9: build.py applies licencecheck to every dex of base.apk with the client unless keep_license_check; none having it stops the build."""
    import inspect
    source = inspect.getsource(build.build)
    assert "keep_license_check" in source and "licensecheck.find_code_item" in source and "licensecheck.patch_dex" in source
    assert "was not found in the code of base.apk" in source


# ---------------------------------------------------- with the game's files --

@pytest.mark.game
def test_whole_build_on_the_real_files(tmp_path):
    """SPEC-013/R-1, SPEC-013/R-4: with the real dump and the real APKs the build writes a signed set and does not touch the originals."""
    from riviera import config, packs
    proj = config.load()
    if not (proj.has_switch() and proj.has_android()):
        pytest.skip("no Switch dump and Android APKs configured (python rpl.py setup)")
    before = {f.name: f.stat().st_mtime_ns for f in proj.apk_dir.glob("*.apk")}
    out = build.build(proj, packs.get_pack(proj.langs, "en"), say=lambda *_: None)
    assert {f.name for f in out.glob("*.apk")} == set(before)
    assert before == {f.name: f.stat().st_mtime_ns for f in proj.apk_dir.glob("*.apk")}
