---
name: data-transform
description: >
  This skill should be used when the user asks to "convert CSV to JSON", "transform data to SQL",
  "turn JSON into a table", "flatten nested JSON", "convert to YAML", "generate INSERT statements",
  "parse and reshape data", "normalize my CSV", "export data as markdown table", "convert
  spreadsheet data", "transform my data format", "change file format", "convert NDJSON to CSV",
  "explode array field", or mentions converting between data formats like CSV, JSON, SQL, YAML,
  XML, TOML, TSV, Markdown tables, or NDJSON. Also use this skill when the user asks to
  "infer schema from data", "detect column types", "what columns are in this file",
  "generate CREATE TABLE from my data", "find null values", or "validate data structure".
  Use this skill any time a user pastes data and wants it in a different format — even if they
  just say "can you turn this into JSON" or "make this a table" without naming a specific format.
version: 1.1.0
---

# Data Transform

Convert data between CSV, JSON, SQL, YAML, Markdown tables, TOML, TSV, and NDJSON
with two bundled Python scripts. Handles encoding detection, type inference, null
normalization, nested-object flattening, array explosion, and large-file streaming —
zero external dependencies needed.

## Quick Start

```bash
# Basic conversion
python scripts/transform.py data.csv --to json
python scripts/transform.py data.json --to sql --table users
python scripts/transform.py data.csv --to markdown

# Flatten nested JSON before converting to CSV
python scripts/transform.py nested.json --to csv --flatten

# Explode an array field (one row per element)
python scripts/transform.py orders.json --to csv --explode items

# Understand your data first
python scripts/infer_schema.py data.csv --output summary

# Stream a large file without loading it all into memory
python scripts/transform.py big.csv --to ndjson --stream

# Pipe from stdin
cat records.ndjson | python scripts/transform.py --from ndjson --to csv
```

## Format Support Matrix

| From \ To  | CSV | JSON | NDJSON | SQL | YAML | Markdown | TOML |
|------------|:---:|:----:|:------:|:---:|:----:|:--------:|:----:|
| CSV / TSV  |  ✓  |  ✓   |   ✓    |  ✓  |  ✓   |    ✓     |  ✓   |
| JSON       |  ✓  |  —   |   ✓    |  ✓  |  ✓   |    ✓     |  ✓   |
| NDJSON     |  ✓  |  ✓   |   —    |  ✓  |  ✓   |    ✓     |  —   |
| YAML       |  ✓  |  ✓   |   ✓    |  ✓  |  —   |    ✓     |  —   |

## Key Options: transform.py

| Flag | Default | Purpose |
|------|---------|---------|
| `--to` | *(required)* | Output format: `json` `ndjson` `csv` `tsv` `sql` `yaml` `markdown` `toml` |
| `--from` | auto | Force input format when piping stdin |
| `--table` | `data` | Table name for SQL output |
| `--dialect` | `sqlite` | SQL dialect: `sqlite` `mysql` `postgres` |
| `--batch` | `500` | Rows per SQL INSERT statement |
| `--delimiter` | `,` | Input CSV field delimiter |
| `--no-header` | false | Input CSV has no header row |
| `--null-values` | `null,NULL,N/A,…` | Comma-separated strings to treat as NULL |
| `--flatten` | false | Recursively flatten nested JSON objects |
| `--sep` | `__` | Key separator for flattened paths (e.g. `address__city`) |
| `--explode FIELD` | — | Expand array field: one row per element. Also accepts a nested path (`user__tags` or `user.tags`); an empty array keeps the row with the field set to null. Runs before `--flatten` |
| `--no-infer` | false | Keep all values as strings (skip type inference) |
| `--stream` | false | Write rows as they are read (CSV/TSV/NDJSON output). CSV/TSV/NDJSON input is read row by row; JSON/YAML input is still parsed whole. CSV columns come from the first row (a warning lists columns dropped later) |
| `--pretty` | false | Pretty-print JSON output |
| `--encoding` | auto | Force input encoding (e.g. `latin-1`, `cp1252`) |
| `-o FILE` | stdout | Write output to file instead of stdout |

## Key Options: infer_schema.py

| Flag | Default | Purpose |
|------|---------|---------|
| `--output` | `json-schema` | Output mode: `json-schema` `sql` `summary` |
| `--table` | `data` | Table name for SQL output |
| `--sample` | `1000` | Max rows to analyze |
| `--enum-threshold` | `20` | Max unique values before dropping enum detection |

## Recommended Workflow for Unknown Data

Run these three commands in sequence before committing to a conversion:

```bash
# 1. Inspect what you have
python scripts/infer_schema.py myfile.csv --output summary

# 2. Preview the conversion
python scripts/transform.py myfile.csv --to markdown | head -20

# 3. Run the real conversion
python scripts/transform.py myfile.csv --to json --pretty -o output.json
```

## Handling Common Edge Cases

**Encoding problems** — The script auto-detects UTF-8 and Latin-1. For Windows
files, pass `--encoding cp1252`. For UTF-8 with BOM, the auto-detector handles it.

**Semicolon-delimited CSV** (common in European Excel exports) — pass `--delimiter ";"`.

**Custom null values** — extend the default list: `--null-values "null,NULL,N/A,#N/A,-,unknown"`.

**Numbers stored as strings** — type inference is on by default; pass `--no-infer` to
keep everything as string (useful before a SQL COPY load where the schema is already defined).

**Nested JSON to SQL** — chain `--flatten` with `--to sql` to produce a flat table with
double-underscore column names (`address__city`, `address__zip`).

**One row per order item** — use `--explode items` where `items` is the array field name.

**Files > 100 MB** — use `--stream` with NDJSON/CSV input and NDJSON/CSV output. Convert big JSON arrays to NDJSON first, because JSON input is parsed as a whole.

**PostgreSQL COPY format** — use `--dialect postgres` with `--to csv` then import with
`\COPY tablename FROM 'file.csv' CSV HEADER;`.

## Type Inference Rules

When `--no-infer` is not set, string values are parsed in this order:

1. **NULL** — value is in the `--null-values` list or is an empty string → `None`
2. **Boolean** — case-insensitive `true/false/yes/no/on/off` → `True`/`False`
3. **Integer** — plain ASCII digits, optional sign, no leading zeros (`007` and ZIP codes like `01234` stay strings, as does `1_000`) → `int`
4. **Float** — decimal or scientific notation (`41.5`, `1e5`, `.5`) → `float`. `nan` and `inf` stay strings, because they are not valid JSON numbers
5. **String** — everything else

SQL output promotes types per column: if a column has mixed int and float values,
the whole column becomes REAL/DOUBLE.

## Additional Resources

### Reference Files

- **`references/format-specs.md`** — Per-format edge cases: CSV quirks, JSON
  null handling, SQL dialect differences, YAML boolean gotchas, encoding notes.
- **`references/transform-patterns.md`** — Ready-to-run recipes: normalizing
  API responses, log analysis, database seed data, pivot-style reshaping, joining two
  CSVs, batch processing a directory of files.

### Scripts

- **`scripts/transform.py`** — Main conversion engine. Run with `--help` for full usage.
- **`scripts/infer_schema.py`** — Schema inference. Outputs JSON Schema draft-07,
  SQL DDL, or a human-readable column summary with type, nullability, and sample values.
