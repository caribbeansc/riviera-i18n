"""SPEC-007: the command line."""

import json
import zipfile

import pytest

from riviera import cli


@pytest.fixture
def env(tmp_path, monkeypatch, langs):
    home = tmp_path / "rplhome"
    home.mkdir()
    monkeypatch.setenv("RPL_HOME", str(home))
    monkeypatch.setenv("RPL_LANGS", str(langs.dir))
    for var in ("RPL_EXEFS", "RPL_ROMFS", "RPL_APK_DIR"):
        monkeypatch.delenv(var, raising=False)
    return home


def run(capsys, *argv):
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_langs_lists_the_packs(env, capsys):
    """SPEC-007/R-1"""
    code, out = run(capsys, "langs")
    assert code == 0 and "xx" in out and "switch" in out


def test_help_names_every_command(capsys):
    """SPEC-007/R-1"""
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for command in ("setup", "doctor", "langs", "switch", "android", "saves", "unpack", "extract", "newlang", "sync", "validate"):
        assert command in out


def test_setup_saves_the_dump_and_doctor_sees_it(env, dump, capsys):
    """SPEC-007/R-2"""
    code, out = run(capsys, "setup", "--exefs", str(dump.exefs), "--romfs", str(dump.romfs))
    assert code == 0
    saved = json.loads((env / "rpl.config.json").read_text(encoding="utf-8"))
    assert saved["exefs"] == str(dump.exefs.resolve()) and saved["romfs"] == str(dump.romfs.resolve())
    assert "synthetic" in out or "07432F48" not in out                      # the doctor printed the build it found


def test_setup_checks_the_folders(env, tmp_path, capsys):
    """SPEC-007/R-2"""
    code, out = run(capsys, "setup", "--exefs", str(tmp_path), "--romfs", str(tmp_path))
    assert code == 1 and "does not look like" in out
    code, out = run(capsys, "setup", "--exefs", str(tmp_path))
    assert code == 1 and "both" in out


def test_build_install_package_end_to_end(env, dump, tmp_path, capsys):
    """SPEC-007/R-3"""
    run(capsys, "setup", "--exefs", str(dump.exefs), "--romfs", str(dump.romfs))
    code, out = run(capsys, "switch", "build", "xx")
    assert code == 0 and "mod written to" in out
    assert (env / "build" / "switch" / "xx" / "exefs").is_dir()
    mods = tmp_path / "mods"
    code, out = run(capsys, "switch", "install", "xx", "--to", str(mods))
    assert code == 0 and (mods / "Test_XX" / "romfs" / "data.bin").is_file()
    zip_path = tmp_path / "out.zip"
    code, out = run(capsys, "switch", "package", "xx", "--zip", str(zip_path))
    assert code == 0 and "atmosphere/contents/01007D6025CB6000/romfs/data.bin" in zipfile.ZipFile(zip_path).namelist()


def test_building_without_a_dump_says_what_to_do(env, capsys):
    """SPEC-007/R-4"""
    code, out = run(capsys, "switch", "build", "xx")
    assert code == 1 and "setup" in out


def test_an_unknown_language_is_reported(env, dump, capsys):
    """SPEC-007/R-4"""
    run(capsys, "setup", "--exefs", str(dump.exefs), "--romfs", str(dump.romfs))
    code, out = run(capsys, "switch", "build", "nope")
    assert code == 1 and "no language pack" in out


def test_a_pack_must_cover_the_platform(env, tmp_path, langs, capsys):
    """SPEC-007/R-4"""
    import synth
    synth.make_lang(langs.dir, "ww", {}, images=False, meta={"platforms": {"android": {}}})
    code, out = run(capsys, "switch", "build", "ww")
    assert code == 1 and "does not cover switch" in out


def test_install_without_any_emulator_explains_the_options(env, dump, monkeypatch, capsys):
    """SPEC-007/R-5"""
    run(capsys, "setup", "--exefs", str(dump.exefs), "--romfs", str(dump.romfs))
    run(capsys, "switch", "build", "xx")
    monkeypatch.setattr(cli.config, "detect_mod_targets", lambda *a, **k: [])
    code, out = run(capsys, "switch", "install", "xx")
    assert code == 1 and "--to" in out and "--adb" in out


def test_doctor_flags_game_text_in_a_pack(env, langs, capsys):
    """SPEC-007/R-6"""
    (langs.dir / "xx" / "text.jsonl").write_text(json.dumps({"k": "0" * 16, "t": ["日本語"]}, ensure_ascii=False) + "\n", encoding="utf-8")
    code, out = run(capsys, "doctor")
    assert code == 1 and "look like game text" in out


def test_the_menu_quits_on_zero(env, monkeypatch, capsys):
    """SPEC-007/R-7"""
    monkeypatch.setattr("builtins.input", lambda *a: "0")
    assert cli.main([]) == 0


def test_the_menu_survives_ctrl_c(env, monkeypatch, capsys):
    """SPEC-007/R-7"""
    def boom(*a):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", boom)
    assert cli.main([]) == 0


def test_saves_hands_the_rest_of_the_command_line_to_the_converter(env, tmp_path, capsys):
    """SPEC-007/R-8"""
    code, out = run(capsys, "saves", "--help")
    assert code == 0 and "verify" in out and "switch2android" in out
    code, out = run(capsys, "saves", "verify", str(tmp_path / "nothing"))
    assert code == 1                                                        # the converter's own exit code, with its own message

