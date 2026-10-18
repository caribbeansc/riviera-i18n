# Contributing

Two kinds of contribution, with different rules: **translations** and **code**.

## The one hard rule

**Never commit anything that came out of the game.** Not the script (English or Japanese), not a picture, not a container, not a
screenshot of the original text in an issue.

This is what keeps the repository redistributable, and it is enforced, not trusted:

```
python rpl.py doctor              # scans langs/ for text that looks like the game's
pytest tests/test_packs.py        # the same check, as a test
```

`rpl.py sync` refuses to write a translation that still contains Japanese, Korean, Chinese or full-width characters, and `work/`,
`build/` and `rpl.config.json` are in `.gitignore`. Leave them there.

## Translations

Start from [docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md); for Spanish read [langs/es/GLOSSARY.md](langs/es/GLOSSARY.md) first.
Before opening a pull request:

```
python rpl.py sync <lang>
python rpl.py validate <lang>
python rpl.py doctor
```

- Commit only `langs/<lang>/`.
- Fix every error `validate` reports. Warnings are judgement calls: "long" on a dialogue line is usually fine, on a menu help line it
  is worth checking in the game.
- Look at the result in the game (or say you did not). A line can pass every check and still hug the edge of a box.
- Say who you are and how the text was produced in the pull request. If it was machine-generated, say so and say how much of it you
  checked. An honest "generated, skimmed, not play-tested" is far more useful to the next person than silence.

Improving an existing language is just as welcome as adding a new one. Small, focused pull requests ("fix the menu help of block 37")
are easier to review than one that rewrites everything.

## Code

The project is **spec-first**. Every non-obvious behaviour is a numbered requirement in [docs/specs/](docs/specs/), and every
requirement has at least one test that names it (`tests/test_specs.py` checks it).

So, in order:

1. Change the spec, in its own commit, if the behaviour changes.
2. Add or update the test that references the requirement (`SPEC-006/R-4`).
3. Change the implementation.

```
pip install -r requirements-dev.txt
pytest -m "not game"       # no game files needed; must stay green
pytest                     # includes the tests that need your own dump
```

House rules that are not negotiable, because each one has burned this project once:

- **Check a rule of the engine with a probe before you write it down**, and read the probe on a capture of the screen, not in the
  string. Several rules in [docs/PIPELINE.md](docs/PIPELINE.md) were believed for hours and were wrong.
- **Never overwrite or reuse a string the code uses by itself** (`riviera.ips.code_uses`); one such write made the game die three
  seconds after booting.
- **Read back what you wrote.** Every patch step verifies its output (`switch build` applies the IPS and reads every string back).
- **A rule that "does not cut" is not "looks right".** Look at the whole capture.
- **Do not reorder build steps.** Later steps read what earlier ones wrote.
- **The build must stay reproducible**: the same dump and pack give the same bytes (a test pins the checksum of the patch). If you
  change the pack or the composer on purpose, update the pinned value in the same commit and say why.

Style: the code reads like prose and the comments explain *why*, not *what*. Docstrings and identifiers are in English so
contributors who do not speak Spanish can work on it; the language packs are where other languages live.

## Reporting a bug

Include:

- what you ran, and the output;
- your platform and Python version (`python rpl.py doctor` prints both);
- whether your game files came from an emulator extraction or a backup, and which version.

Do not attach game files or the original text of the game.
