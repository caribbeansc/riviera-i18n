"""The graphical patcher only builds command lines for the CLI, so what can be tested without a display is tested here."""

import subprocess
import sys
from pathlib import Path

import gui

ROOT = Path(__file__).resolve().parent.parent


def test_the_window_runs_the_same_commands_as_the_terminal():
    assert gui.setup_argv("backup", backup="g.xci", keys="p.keys") == ["setup", "--xci", "g.xci", "--keys", "p.keys"]
    assert gui.setup_argv("backup", backup="g.xci") == ["setup", "--xci", "g.xci"]
    assert gui.setup_argv("folders", exefs="e", romfs="r") == ["setup", "--exefs", "e", "--romfs", "r"]
    assert gui.switch_argv("build", "es") == ["switch", "build", "es"]
    assert gui.switch_argv("install", "es", "/mods") == ["switch", "install", "es", "--to", "/mods"]
    assert gui.android_argv("build", "en", keep_license_check=True) == ["android", "build", "en", "--keep-license-check"]
    assert gui.android_argv("install", "es", serial="X") == ["android", "install", "es", "--serial", "X"]


def test_every_command_it_builds_is_a_real_command():
    from riviera import cli
    parser = cli.build_parser()
    for argv in (gui.setup_argv("backup", backup="a.xci"), gui.setup_argv("folders", exefs="e", romfs="r"),
                 gui.switch_argv("build", "es"), gui.switch_argv("install", "es", "/m"), ["switch", "package", "es"],
                 gui.android_argv("build", "es", True), gui.android_argv("install", "es", serial="S"), ["setup", "--apk-dir", "d"]):
        assert parser.parse_args(argv).command


def test_the_selftest_passes_from_a_checkout():
    done = subprocess.run([sys.executable, str(ROOT / "gui.py"), "--selftest"], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "selftest: ok" in done.stdout
