# Changelog

## Unreleased
- **Unknown input extensions are refused.** `data.xml` (or `.toml`, `.md`) used to be read as CSV and gave `[]` or garbage without a message. Now the script says which input formats exist and points to `--from`. `.txt`, `.dat` and no extension still count as CSV.
- **Docs matched to the code.** The skill description offered XML, which was never supported; SKILL.md and README now state the real input and output formats, and that YAML input needs PyYAML. The format table is verified cell by cell by tests (NDJSON/YAML to TOML work and were wrongly shown as unsupported). 97 tests.

## 1.1.0
Fixes for behaviour that the documentation promised but the code did not deliver:
- **Type inference corrupted IDs.** ZIP codes and IDs with leading zeros (`01234`) came back as `1234.0`, `1_000` as `1000.0`. Numbers are now matched with strict ASCII syntax; ambiguous values stay text. `infer_schema.py` uses the same rules (it used to propose INTEGER columns for ZIP codes).
- **`nan` / `inf` produced invalid JSON** (`NaN`, `Infinity`). They now stay strings.
- **`--flatten --explode` did nothing**, because flatten turned the arrays into strings first. Explode now runs first and accepts nested paths (`user__tags` or `user.tags`). Empty arrays keep their row instead of dropping it.
- **TOML output was invalid** for nested objects (JSON syntax instead of inline tables) and for strings with newlines or control characters. Output now parses with a TOML 1.0 parser.
- **`--stream` kept everything in memory.** It now writes rows as they are read, and warns when later rows contain columns the first row did not have.
- CSV output writes booleans as `true`/`false` like every other writer (it printed `True`/`False`).
- 52 tests (`pytest`), MIT licence added.

## 1.0.0
- First version.
