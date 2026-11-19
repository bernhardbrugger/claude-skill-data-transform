# Contributing to data-transform

Bug reports, wrong conversions and pull requests are all welcome.

## Set up and run the tests

```bash
git clone https://github.com/bernhardbrugger/claude-skill-data-transform.git
cd claude-skill-data-transform
python -m venv .venv            # .venv/Scripts/activate on Windows, source .venv/bin/activate elsewhere
pip install pytest pyyaml       # the scripts themselves need only the standard library
pytest -q                       # or one area: pytest -q -k explode
```

The tests run `skills/data-transform/scripts/transform.py` as a subprocess and import it as a module, so there is
nothing to install. CI runs the same `pytest` on Linux and Windows with Python 3.8, 3.9 and 3.12; do not use syntax
or standard-library features newer than 3.8 in the scripts (no `match`, no `X | None`, no `list[str]` at runtime).

To try a change by hand:

```bash
python skills/data-transform/scripts/transform.py data.csv --to sql --dialect postgres
python skills/data-transform/scripts/infer_schema.py data.csv --output summary
```

## Reporting a bug

Open an issue with:

- the smallest input file that shows the problem (a few rows are enough; remove anything private),
- the exact command you ran,
- the output you got and the output you expected (for SQL: which database and the error it gave when loading),
- your Python version and OS, and whether PyYAML is installed.

## Pull requests

- One change per pull request, with a test in `tests/test_transform.py` that fails without it.
- Check output the way a user would consume it, not against the script's own idea of it: parse JSON strictly
  (`strict_json` in the tests rejects `NaN`), parse TOML with `tomllib`, and load SQL into SQLite.
- `transform.py` and `infer_schema.py` must agree on types: if one changes how a column is typed, the other changes
  with it, and a test converts the same file with both.
- The scripts stay standard-library only; PyYAML stays optional (YAML input and high-fidelity YAML output).
- Add a line under `## Unreleased` in `CHANGELOG.md` when users would notice the change. If a README example's output
  changes, run the example and paste the real output. If the change affects what Claude should do, update
  `skills/data-transform/SKILL.md` too.
- Commit messages say what changed and why (`fix: ...`, `docs: ...`, `ci: ...`).

## Out of scope

XML, TOML and Markdown are output-only, and Excel files are not read. Please open an issue first if you want to
change that, so we can agree on the approach.

By contributing you agree that your work is released under the MIT licence of this project.
