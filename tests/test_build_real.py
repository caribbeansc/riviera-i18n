"""SPEC-006: the build against a real dump of the game. Skipped unless you have run ``python rpl.py setup``.

The checks are on *derived* facts (counts, verification, a checksum of the patch): none of them carries the game's text.
"""

import hashlib
import tempfile

import pytest

from riviera import builds, packs, sge
from riviera.nso import Nso
from riviera.switch import build as sb

pytestmark = pytest.mark.game

#: MD5 of the Spanish patch for the v1.0.0 executable. If the pack or the composer change on purpose, update it in the same
#: commit and say why; if they did not, a mismatch means the build is no longer reproducible.
SPANISH_IPS_MD5 = "0238670de7b1acca156ad725d25f0b16"


@pytest.fixture(scope="module")
def result(request):
    from riviera import config
    proj = config.load()
    if not proj.has_switch():
        pytest.skip("no Switch dump configured")
    try:
        builds.for_nso(Nso(proj.exefs / "main"))
    except builds.UnknownBuild as e:
        pytest.skip(str(e))
    pack = packs.get_pack(proj.langs, "es")
    tmp = tempfile.TemporaryDirectory()
    report = sb.build(proj, pack, out_dir=tmp.name, say=lambda m: None)
    request.addfinalizer(tmp.cleanup)
    return proj, report


def test_the_spanish_mod_builds_cleanly(result):
    """SPEC-006/R-13"""
    _, report = result
    s = report.summary
    assert report.ok and s["no_room"] == 0 and s["verification_failures"] == 0
    assert s["overflow"] == 0 and s["segments_mismatch"] == 0
    assert s["rows_translated"] == 16723 and s["pictures_replaced"] == 200
    assert not report.warnings, report.warnings[:3]


def test_the_patch_is_reproducible(result):
    """SPEC-006/R-13"""
    _, report = result
    patch = next((report.out_dir / "exefs").glob("*.ips")).read_bytes()
    assert hashlib.md5(patch).hexdigest() == SPANISH_IPS_MD5


def test_the_containers_open_and_carry_the_changes(result):
    """SPEC-006/R-13"""
    proj, report = result
    with sge.Archive(report.out_dir / "romfs" / "data.bin") as new, sge.Archive(proj.romfs / "data.bin") as old:
        assert sorted(new.paths()) == sorted(old.paths())
    with sge.Archive(report.out_dir / "romfs" / "data_en.bin") as new, sge.Archive(proj.romfs / "data_en.bin") as old:
        assert sorted(new.paths()) == sorted(old.paths())
        assert new.read_path("data/event/demo1.pck") != old.read_path("data/event/demo1.pck")


def test_the_script_of_the_pack_matches_the_game(result):
    """SPEC-005/R-5: every key of the pack that the game has is checked against the game's markers and segments."""
    proj, report = result
    from riviera import workflow
    from riviera.nso import read_rows
    units = workflow.units_of(read_rows(Nso(proj.exefs / "main")))
    errors, warns, checked = workflow.validate_pack(proj, packs.get_pack(proj.langs, "es"), units, None)
    assert errors == [], errors[:5]
    assert checked > 11000
