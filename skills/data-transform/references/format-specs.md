# Format Specifications & Edge Cases

Reference for per-format gotchas, encoding quirks, and dialect differences.
Read this file when the task involves non-obvious format behaviour.

---

## CSV / TSV

### Encoding
- **UTF-8 with BOM** (`utf-8-sig`) — common from Excel on Windows. `detect_encoding()` handles this automatically via the `utf-8-sig` probe.
- **Latin-1 / cp1252** — common from legacy European systems. Latin-1 is tried as the fallback after UTF-8 fails.
- **Force with** `--encoding cp1252` (German/French Windows), `--encoding iso-8859-1` (Western European Linux).

### Delimiter variants
| Source               | Delimiter | Flag              |
|----------------------|-----------|-------------------|
| Standard CSV         | `,`       | *(default)*        |
| European Excel       | `;`       | `--delimiter ";"`  |
| TSV / tab-separated  | `\t`      | `--to tsv` / `.tsv` extension |
| Pipe-separated       | `\|`      | `--delimiter "\|"` |

### Quoted fields
Python's `csv` module follows RFC 4180. Quoted fields may contain:
- Commas or the delimiter character
- Embedded newlines (the row spans multiple physical lines)
- Double-quote escape: `""` inside a quoted field represents one `"`

### Null / empty cells
An empty CSV cell (`,,`) becomes empty string `""`, which is always treated as `None` regardless of `--null-values`.

### No-header CSVs
Pass `--no-header`. Columns are named `col0`, `col1`, … Use with caution — type inference still runs but column names are meaningless until renamed.

### Excel quirks
- Dates exported from Excel often arrive as `MM/DD/YYYY` (`01/31/2024`), which the date pattern detector recognises.
- Numbers with thousands separators (`1,234.56`) are **not** auto-converted to float — they stay as strings. Strip commas before conversion.
- Currency symbols (`$1.99`) stay as strings.

---

## JSON

### Root structure
The script accepts:
- **Array of objects** — `[{"k": "v"}, …]` → natural tabular form
- **Single object** — `{"k": "v"}` → treated as one row
- Nested objects are supported; use `--flatten` to unroll them to CSV/SQL.

### Nested objects → CSV
`--flatten` joins keys with the separator (default `__`):
```json
{"user": {"name": "Alice", "city": "NY"}}
```
→ columns `user__name`, `user__city`

Use `--sep .` to get `user.name` instead.

### Arrays inside JSON rows
By default, array values are JSON-stringified into a single cell when converting to CSV/SQL.
Use `--explode FIELD` to produce one row per array element:
```bash
transform.py orders.json --to csv --explode items
transform.py orders.json --to csv --flatten --explode customer__tags   # nested path
```

An empty array keeps the row (the field becomes null), so no row disappears silently.

### Large JSON arrays
For JSON files over ~50 MB, prefer NDJSON (one JSON object per line) so `--stream` works.
To convert a big JSON array to NDJSON first:
```bash
transform.py big.json --to ndjson -o big.ndjson
transform.py big.ndjson --to csv --stream
```

### Null values in JSON
JSON `null` is already `None` in Python — no null-value lookup needed. The `--null-values` flag only affects string-typed inputs (CSV/TSV).

### Numbers
JSON numbers map to Python `int` or `float` directly. Very large integers (> 2⁵³) may lose precision when round-tripping through JSON.

---

## NDJSON (newline-delimited JSON / JSON Lines)

Each line is an independent JSON object. Blank lines are skipped. This format is ideal for:
- Streaming large datasets
- Log files (`{"ts": "…", "level": "info", "msg": "…"}`)
- API response streams

### Usage
Files with `.ndjson` or `.jsonl` extension are auto-detected.
Pipe support: `cat app.log | transform.py --from ndjson --to csv`

---

## SQL

### Dialect differences

| Feature       | SQLite           | MySQL              | PostgreSQL           |
|---------------|------------------|--------------------|----------------------|
| Identifier quote | `"col"`       | `` `col` ``        | `"col"`              |
| Boolean        | `INTEGER` 0/1   | `TINYINT(1)` 0/1   | `BOOLEAN` TRUE/FALSE |
| Float type     | `REAL`           | `DOUBLE`           | `DOUBLE PRECISION`   |
| Null-safe eq   | `IS NULL`        | `IS NULL`          | `IS NULL`            |
| String escape  | `''`             | `''` + `\\`        | `''`                 |

### CREATE TABLE
The script emits `CREATE TABLE IF NOT EXISTS`. For PostgreSQL, you may want to add `ON CONFLICT` handling separately.

### INSERT batching
Large datasets are split into batches of `--batch N` rows per `INSERT INTO … VALUES` statement (default 500). Tune per dialect:
- **SQLite**: 500–1000 (SQLITE_MAX_VARIABLE_NUMBER default is 999)
- **MySQL**: 1000–5000 (max_allowed_packet dependent)
- **PostgreSQL**: 1000–10000 (no hard limit, limited by memory)

### Type inference → SQL types
| Inferred Python type | SQLite   | MySQL        | PostgreSQL       |
|----------------------|----------|--------------|------------------|
| `bool`               | INTEGER  | TINYINT(1)   | BOOLEAN          |
| `int`                | INTEGER  | INT          | INTEGER          |
| `float`              | REAL     | DOUBLE       | DOUBLE PRECISION |
| date string          | TEXT     | DATE         | DATE             |
| everything else      | TEXT     | TEXT         | TEXT             |

Columns with **mixed** int + float → promoted to REAL / DOUBLE.

### PostgreSQL COPY (fast bulk load)
For bulk loading, export to CSV then use `\COPY`:
```bash
transform.py data.json --to csv -o data.csv
psql -c "\COPY tablename FROM 'data.csv' CSV HEADER;"
```

---

## YAML

### PyYAML dependency
YAML **input** and full-fidelity YAML **output** require `pip install pyyaml`.
Without PyYAML, a minimal stdlib fallback handles flat dicts for output only.

### YAML boolean gotcha
PyYAML 5.x parses `yes`, `no`, `on`, `off`, `true`, `false` as booleans.
This can surprise users who have CSV columns named "Status" with values `yes`/`no`.
If this is undesirable, use `--no-infer` to keep everything as strings before converting to YAML.

### Multiline strings
PyYAML auto-selects block scalars (`|`) for strings containing newlines, which is correct but can look unexpected. This is standard YAML.

---

## Markdown tables

### Pipe character in values
Literal `|` inside a cell is escaped to `\|` automatically.

### Newlines in values
Embedded newlines are replaced with a space — Markdown tables are single-line per row.

### No nested structure
Dict and list values are JSON-stringified into a single cell. For readability, flatten before converting to Markdown.

### Rendering
Markdown tables use CommonMark GFM pipe-table syntax, compatible with:
GitHub, GitLab, VS Code preview, Obsidian, Notion, Confluence.

---

## TOML

### No null
TOML 1.0 has no null type. Columns with `None` values are **omitted** from the TOML output for that record.

### Output structure
Each row becomes an `[[record]]` array-of-tables entry. Keys are always double-quoted. Nested objects are written as TOML inline tables (`{ "name" = "Anna" }` style), arrays as TOML arrays, and strings are escaped (quotes, backslashes, newlines, control characters), so the output parses with any TOML 1.0 parser.

### TOML is suitable for
Config files, small reference tables. It is **not** suitable for large datasets — use JSON or CSV instead.

---

## Encoding Quick Reference

| Encoding    | Common source                           | `--encoding` flag  |
|-------------|-----------------------------------------|--------------------|
| `utf-8`     | Modern systems, APIs                    | *(auto-detected)*  |
| `utf-8-sig` | Excel on Windows (BOM prefix)           | *(auto-detected)*  |
| `latin-1`   | Unix legacy, French/Spanish systems     | *(auto-fallback)*  |
| `cp1252`    | Windows Western European                | `--encoding cp1252`|
| `cp1251`    | Windows Cyrillic                        | `--encoding cp1251`|
| `gbk`       | Chinese Windows                         | `--encoding gbk`   |
| `shift_jis` | Japanese systems                        | `--encoding shift_jis` |
