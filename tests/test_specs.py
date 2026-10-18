"""The specs and the tests agree: every requirement is named by a test, and every ID a test names exists."""

import re
from pathlib import Path

SPECS = Path(__file__).resolve().parent.parent / "docs" / "specs"
TESTS = Path(__file__).resolve().parent

REF = re.compile(r"SPEC-(\d+)/((?:R-\d+(?:,\s*)?)+)")


def defined() -> set[str]:
    out = set()
    for f in SPECS.glob("SPEC-*.md"):
        num = re.match(r"SPEC-(\d+)", f.name).group(1)
        for m in re.finditer(r"^- \*\*R-(\d+)\*\*", f.read_text(encoding="utf-8"), re.M):
            out.add(f"{num}/R-{m.group(1)}")
    return out


def referenced() -> set[str]:
    out = set()
    for f in TESTS.glob("test_*.py"):
        for m in REF.finditer(f.read_text(encoding="utf-8")):
            for r in re.findall(r"R-(\d+)", m.group(2)):
                out.add(f"{m.group(1)}/R-{r}")
    return out


def test_every_requirement_is_covered_by_a_test():
    missing = sorted(defined() - referenced())
    assert not missing, f"requirements with no test: {missing}"


def test_every_id_a_test_names_exists():
    unknown = sorted(referenced() - defined())
    assert not unknown, f"tests name requirements that no spec defines: {unknown}"


def test_every_spec_is_listed_in_the_index():
    index = (SPECS / "README.md").read_text(encoding="utf-8")
    for f in SPECS.glob("SPEC-*.md"):
        assert f.name in index, f"{f.name} is not in docs/specs/README.md"
