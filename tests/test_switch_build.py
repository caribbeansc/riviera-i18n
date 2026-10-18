"""SPEC-006: building, installing and packaging the Switch mod (on a synthetic game)."""

import json
import stat
import sys
import zipfile

import pytest
from PIL import Image

import synth
from riviera import builds, config, font, ips, pck, sge
from riviera import nso as N
from riviera.switch import build as sb
from riviera.switch import install as si


@pytest.fixture
def built(project, langs):
    report = sb.build(project, langs.pack, say=lambda m: None)
    assert report.ok, report.summary
    return report


def test_build_writes_every_file(built, dump):
    """SPEC-006/R-1"""
    out = built.out_dir
    assert sorted(p.name for p in (out / "exefs").glob("*.ips")) == sorted(n + ".ips" for n in set(dump.build.ips_names))
    assert (out / "romfs" / "data.bin").is_file() and (out / "romfs" / "data_en.bin").is_file() and (out / "report.json").is_file()
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["verification_failures"] == 0 and report["summary"]["language"] == "xx"


def test_both_ips_names_hold_the_same_patch(built, dump):
    """SPEC-006/R-2: Eden and yuzu look for the full id, Ryujinx and Atmosphère for its first 16 bytes."""
    a, b = (built.out_dir / "exefs" / f"{n}.ips" for n in dump.build.ips_names)
    assert a.read_bytes() == b.read_bytes()
    assert len(dump.build.ips_names[1]) == 32


def test_the_patched_executable_speaks_the_translation(built, dump):
    """SPEC-006/R-3"""
    n = N.Nso(dump.exefs / "main")
    patched = N.Nso.from_image(ips.apply_ips((built.out_dir / "exefs" / f"{dump.build.ips_names[0]}.ips").read_bytes(), n.image),
                               dump.build.build_id)
    rows = {(r["block"], r["row"]): r["en"] for r in N.read_rows(patched)}
    assert rows[(0, 0)] == "Hola"
    assert rows[(1, 0)] == "Sí" and rows[(1, 1)] == "No"
    voiced = rows[(0, 1)].replace(";", "").replace("\n", "")
    assert voiced == "V(112b_0000)¿Cómo estás hoy?,V(112b_0001)amigo"
    assert rows[(0, 2)] == "Pulsa el botón B1"                           # the marker travels with the text


def test_the_other_languages_of_the_table_are_left_alone(built, dump):
    """SPEC-006/R-3"""
    n = N.Nso(dump.exefs / "main")
    patched = N.Nso.from_image(ips.apply_ips((built.out_dir / "exefs" / f"{dump.build.ips_names[0]}.ips").read_bytes(), n.image))
    assert [r["jp"] for r in N.read_rows(patched)] == [r["jp"] for r in N.read_rows(n)]


def test_romfs_gets_the_atlas_and_the_pictures(built, dump):
    """SPEC-006/R-4"""
    with sge.Archive(built.out_dir / "romfs" / "data.bin") as arc:
        _, ents = pck.read_pck(arc.read_path(font.ATLAS_PCK))
        import io
        assert Image.open(io.BytesIO(ents[0][1])).size[1] == font.ROWS * font.CELL
        assert arc.read_path("data/readme.txt") == b"hello"                # everything else is carried over
    with sge.Archive(built.out_dir / "romfs" / "data_en.bin") as arc:
        ents = dict((pck.entry_name(n), b) for n, b in pck.read_pck(arc.read_path("data/event/demo.pck"))[1])
        assert Image.open(io.BytesIO(ents["story_00.webp"])).size == (40, 12)
        assert arc.read_path("data/readme.txt") == b"hi"


def test_the_build_is_reproducible(project, langs, built):
    """SPEC-006/R-5"""
    again = sb.build(project, langs.pack, out_dir=project.root / "again", say=lambda m: None)
    for rel in ("exefs/" + built.out_dir.joinpath("exefs").iterdir().__next__().name, "romfs/data.bin", "romfs/data_en.bin"):
        assert (built.out_dir / rel).read_bytes() == (again.out_dir / rel).read_bytes()


def test_without_romfs_only_the_patch_is_written(project, langs):
    """SPEC-006/R-6"""
    rep = sb.build(project, langs.pack, out_dir=project.root / "x", with_romfs=False, say=lambda m: None)
    assert not (rep.out_dir / "romfs").exists() and list((rep.out_dir / "exefs").glob("*.ips"))


def test_an_unknown_build_is_refused(project, langs, dump, monkeypatch):
    """SPEC-006/R-7: addresses are fixed per build, so a build the toolkit has not seen is not patched blindly."""
    monkeypatch.delitem(builds.SWITCH_BUILDS, dump.build.build_id)
    with pytest.raises(sb.BuildError, match="not supported"):
        sb.build(project, langs.pack, say=lambda m: None)


def test_no_dump_is_a_clear_error(tmp_path, langs):
    """SPEC-006/R-7"""
    proj = config.Project(root=tmp_path, work=tmp_path / "w", build=tmp_path / "b", langs=langs.dir)
    with pytest.raises(config.ConfigError, match="setup"):
        sb.build(proj, langs.pack, say=lambda m: None)


def test_a_pack_without_a_script_is_refused(project, langs, tmp_path):
    """SPEC-006/R-7"""
    empty = synth.make_lang(tmp_path / "other", "yy", {}, images=False)
    with pytest.raises(sb.BuildError, match="no script"):
        sb.build(project, empty, say=lambda m: None)


def test_pictures_made_for_another_version_are_reported(project, langs, dump):
    """SPEC-006/R-8"""
    (dump.romfs / "data_en.bin").write_bytes(synth.build_container({
        "data/event/demo.pck": synth.make_pck({"story_00.webp": synth.webp((16, 8), (1, 1, 1, 255)),
                                               "panel.webp": synth.webp((16, 8), (200, 200, 200, 255))})}))
    rep = sb.build(project, langs.pack, say=lambda m: None)
    assert any("story_00.webp" in w for w in rep.warnings)


# ---- installing --------------------------------------------------------------------------------------------------------------

def test_install_into_a_folder_and_remove(built, tmp_path):
    """SPEC-006/R-9"""
    mod = si.install_to_dir(built.out_dir, tmp_path / "mods" / "Test_XX")
    assert (mod / "exefs").is_dir() and (mod / "romfs" / "data.bin").is_file()
    again = si.install_to_dir(built.out_dir, mod)                         # a second install replaces the first
    assert again == mod
    assert si.remove_from_dir(mod) and not mod.exists() and not si.remove_from_dir(mod)


def test_install_refuses_something_that_is_not_a_built_mod(tmp_path):
    """SPEC-006/R-9"""
    with pytest.raises(si.InstallError, match="not a built mod"):
        si.install_to_dir(tmp_path, tmp_path / "x")


def test_emulator_folders_are_named_per_family(monkeypatch, tmp_path):
    """SPEC-006/R-10: Ryujinx wants a lowercase title id, yuzu and Eden an uppercase one."""
    monkeypatch.setattr(config, "_emulator_roots", lambda: [
        ("Ryujinx", tmp_path / "ry" / "mods" / "contents", "ryujinx"), ("eden", tmp_path / "ed" / "load", "yuzu"),
        ("gone", tmp_path / "nothing", "yuzu")])
    (tmp_path / "ry" / "mods" / "contents").mkdir(parents=True)
    (tmp_path / "ed" / "load").mkdir(parents=True)
    targets = config.detect_mod_targets()
    assert [(t.emulator, t.path.name) for t in targets] == [("Ryujinx", "01007d6025cb6000"), ("eden", "01007D6025CB6000")]


def test_atmosphere_package_layout(built, dump, tmp_path):
    """SPEC-006/R-11"""
    out = si.package_atmosphere(built.out_dir, "Test_XX", tmp_path / "x.zip")
    names = zipfile.ZipFile(out).namelist()
    assert f"atmosphere/exefs_patches/Test_XX/{dump.build.ips_names[1]}.ips" in names
    assert "atmosphere/contents/01007D6025CB6000/romfs/data.bin" in names
    assert "atmosphere/contents/01007D6025CB6000/romfs/data_en.bin" in names


@pytest.mark.skipif(sys.platform == "win32", reason="the fake adb is a shell script")
def test_install_over_adb(built, tmp_path):
    """SPEC-006/R-12"""
    log = tmp_path / "adb.log"
    adb = tmp_path / "adb"
    adb.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\n")
    adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
    target = si.install_android_emulator(built.out_dir, "Test_XX", serial="ABC", adb=str(adb), say=lambda m: None)
    assert target.endswith("/files/load/01007D6025CB6000/Test_XX")
    calls = log.read_text().splitlines()
    assert all(c.startswith("-s ABC ") for c in calls)
    assert any(c.startswith("-s ABC push") and c.endswith("/romfs/") for c in calls)
    assert sum(" push " in c for c in calls) == len(list((built.out_dir / "exefs").glob("*.ips"))) + 2


@pytest.mark.skipif(sys.platform == "win32", reason="the fake adb is a shell script")
def test_install_over_adb_refuses_a_running_emulator(built, tmp_path):
    """SPEC-006/R-12: the files would be in use."""
    adb = tmp_path / "adb"
    adb.write_text("#!/bin/sh\necho 12345\n")
    adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(si.InstallError, match="running"):
        si.install_android_emulator(built.out_dir, "Test_XX", adb=str(adb))
