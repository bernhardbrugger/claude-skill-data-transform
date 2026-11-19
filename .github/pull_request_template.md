<!-- See CONTRIBUTING.md. One change per pull request. -->

## What and why

## How it was tested

- [ ] `pytest -q` passes
- [ ] A test fails without this change (or: why no test is possible)
- [ ] Output is checked the way a user consumes it (strict JSON, `tomllib`, SQL loaded into SQLite), not against the script's own output
- [ ] If typing changed: `transform.py` and `infer_schema.py` still agree

## Docs

- [ ] `CHANGELOG.md` has a line under `## Unreleased` (if users would notice the change)
- [ ] README examples whose output changed were re-run and the real output pasted; `SKILL.md` updated if Claude should act differently
