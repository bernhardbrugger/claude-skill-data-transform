# Changelog

## Unreleased
- **`infer_schema.py` recognises dates like `transform.py` does.** A `2024-03-01` column was `string`/`TEXT` in the schema but `DATE` in `transform.py --to sql --dialect postgres`, so a table made from the schema and the INSERTs disagreed. The schema now says `date` (summary), `DATE` (SQL) and `format: date` (JSON Schema, only for ISO dates); a date column that also holds numbers or text stays text in both scripts. Both use the same four date patterns.
- **CSV types are decided per column.** A ZIP column with `01067` and `80331` came out of `--to json` as one string and one number (`"01067"`, `80331`), and an answer column with `yes` and `maybe` as `true` and `"maybe"`. A column whose values infer to different kinds now keeps its original text in every row; integers and floats still mix. `--stream` types each value on its own, because it cannot look ahead (documented in SKILL.md).
- **SQL output loads into the table it creates.** PostgreSQL output wrote booleans as `1`/`0` into a `BOOLEAN` column, which PostgreSQL rejects (no implicit integer-to-boolean cast); it now writes `TRUE`/`FALSE`. Every value is now a literal of its column's type: a number in a `TEXT` column (a ZIP code column with `01067` and `80331`) is quoted, a boolean in an `INTEGER` column is `1`/`0`, a date column that also holds numbers becomes `TEXT`, and nested objects/arrays are written as JSON instead of Python's `{'a': 1}`. New test loads the output into SQLite.
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
