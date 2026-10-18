# Specifications

This project is developed **spec-first**: every non-obvious behaviour is written down as a numbered requirement *before* it is
implemented, and every requirement has at least one test that references its ID.

| Spec | Title | Tests |
|------|-------|-------|
| [SPEC-001](SPEC-001-containers.md) | `data*.bin` containers and `.pck` packages | `tests/test_sge.py`, `tests/test_pck.py` |
| [SPEC-002](SPEC-002-script.md) | The script in the executable, and the IPS patch | `tests/test_nso.py`, `tests/test_segments.py`, `tests/test_ips.py` |
| [SPEC-003](SPEC-003-image-delta.md) | Translated artwork: full pictures and deltas | `tests/test_images.py`, `tests/test_packs.py` |
| [SPEC-004](SPEC-004-language-pack.md) | Language pack layout | `tests/test_packs.py` |
| [SPEC-005](SPEC-005-translation-keys.md) | Copyright-safe translation keys | `tests/test_packs.py`, `tests/test_workflow.py`, `tests/test_build_real.py` |
| [SPEC-006](SPEC-006-switch-build.md) | Switch build, installation and packaging | `tests/test_switch_build.py`, `tests/test_build_real.py` |
| [SPEC-007](SPEC-007-cli.md) | Command-line interface | `tests/test_cli.py` |
| [SPEC-008](SPEC-008-validator.md) | Translation validator and workflow | `tests/test_validate.py`, `tests/test_workflow.py` |
| [SPEC-009](SPEC-009-composer.md) | The line composer | `tests/test_compose.py` |
| [SPEC-010](SPEC-010-font.md) | The accented letters in the font | `tests/test_font.py` |
| [SPEC-011](SPEC-011-saves.md) | The save-game converter | `tests/test_saves.py` |
| [SPEC-012](SPEC-012-license-check.md) | Switching off the licence check of your own copy | `tests/test_licensecheck.py` |
| [SPEC-013](SPEC-013-android-build.md) | The Android build | `tests/test_android_build.py`, `tests/test_android_apk.py`, `tests/test_android_arsc.py` |
| [SPEC-014](SPEC-014-android-text.md) | The script in the Android library | `tests/test_android_align.py`, `tests/test_android_text.py` |
| [SPEC-015](SPEC-015-android-hooks.md) | Proportional text in the Android library | `tests/test_android_hooks.py`, `tests/test_android_elf.py` |
| [SPEC-016](SPEC-016-android-artwork.md) | The artwork of the Android build | `tests/test_android_images.py`, `tests/test_android_packs.py` |

## How to read a requirement ID

`SPEC-001/R-3` means "requirement 3 of spec 1". Tests name the requirements they cover in their docstring, so `pytest -k R-3`
and `grep -r "SPEC-001/R-3"` both work. `tests/test_specs.py` checks that the two sides agree: every requirement written here is
named by a test, and every ID a test names exists here.

## Rules for changing a spec

1. Change the spec text first, in its own commit.
2. Update or add the tests that reference the changed requirement.
3. Only then change the implementation.

A requirement with no test is a bug in the spec.
