"""Fixtures: a synthetic game (see synth.py) and a language pack for it. No test here needs the real game unless it is marked
``game``, and those are skipped when no dump is configured."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synth  # noqa: E402
from riviera import builds, config  # noqa: E402


@pytest.fixture
def text_es():
    """Translations of the strings of ``synth.sample_blocks()``, keyed by the raw English."""
    return {
        "Hello": ["Hola"],
        "V(112b_0000)How are you today,V(112b_0001)friend?": ["¿Cómo estás hoy?", "amigo"],
        "Press the B1 Button": ["Pulsa el botón B1"],
        "Yes": ["Sí"],
        "No": ["No"],
    }


@pytest.fixture
def dump(tmp_path, monkeypatch):
    """A synthetic Switch dump, registered as a known build."""
    exefs, romfs, nso = synth.make_dump(tmp_path / "dump", synth.sample_blocks())
    monkeypatch.setitem(builds.SWITCH_BUILDS, nso.build.build_id, nso.build)
    return SimpleNamespace(exefs=exefs, romfs=romfs, nso=nso, build=nso.build)


@pytest.fixture
def langs(tmp_path, text_es):
    folder = tmp_path / "langs"
    pack = synth.make_lang(folder, "xx", text_es)
    return SimpleNamespace(dir=folder, pack=pack)


@pytest.fixture
def project(tmp_path, dump, langs):
    root = tmp_path / "home"
    root.mkdir()
    proj = config.Project(root=root, work=root / "work", build=root / "build", langs=langs.dir)
    proj.set_switch(dump.exefs, dump.romfs)
    return proj


def real_project():
    proj = config.load()
    return proj if proj.has_switch() else None


@pytest.fixture
def real():
    proj = real_project()
    if proj is None:
        pytest.skip("no Switch dump configured (python rpl.py setup)")
    return proj


def pytest_collection_modifyitems(config, items):
    pass
