# Changelog

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
