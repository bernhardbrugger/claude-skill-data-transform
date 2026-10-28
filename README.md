# data-transform — Claude Code Skill

**Convert data between any format with a single command.**

CSV · JSON · SQL · YAML · Markdown · TOML · TSV · NDJSON

---

## What it does

This Claude Code skill gives Claude two powerful Python scripts and expert knowledge to handle any data conversion task — reliably, every time, without re-inventing the logic from scratch:

| You ask Claude… | What happens |
|-----------------|--------------|
| "Convert this CSV to JSON" | Runs `transform.py data.csv --to json` |
| "Turn my JSON into SQL INSERT statements" | Runs `transform.py data.json --to sql --table users` |
| "Flatten this nested JSON and export to CSV" | Runs `transform.py api.json --to csv --flatten` |
| "What columns and types are in my data file?" | Runs `infer_schema.py data.csv --output summary` |
| "Generate a CREATE TABLE for this CSV" | Runs `infer_schema.py data.csv --output sql` |
| "Make this a markdown table" | Runs `transform.py data.csv --to markdown` |

**No external dependencies.** Pure Python 3.8+ stdlib. Optional `pip install pyyaml` for YAML input/output.

---

## Format Support

| From \ To  | CSV | JSON | NDJSON | SQL | YAML | Markdown | TOML |
|------------|:---:|:----:|:------:|:---:|:----:|:--------:|:----:|
| CSV / TSV  | ✓   | ✓    | ✓      | ✓   | ✓    | ✓        | ✓    |
| JSON       | ✓   | —    | ✓      | ✓   | ✓    | ✓        | ✓    |
| NDJSON     | ✓   | ✓    | —      | ✓   | ✓    | ✓        | —    |
| YAML       | ✓   | ✓    | ✓      | ✓   | —    | ✓        | —    |

---

## Installation

### Option A — Install as a Claude Code plugin (recommended)

```bash
# Clone the repo
git clone https://github.com/bernhardbrugger/claude-skill-data-transform.git

# Register with Claude Code
claude plugin add ./claude-skill-data-transform
```

### Option B — Manual install

Copy the plugin folder into your Claude Code plugins directory:

```bash
cp -r claude-skill-data-transform ~/.claude/plugins/data-transform
```

### Option C — Use scripts standalone

The scripts work on their own without Claude:

```bash
python skills/data-transform/scripts/transform.py data.csv --to json
python skills/data-transform/scripts/infer_schema.py data.csv --output summary
```

---

## Quick Examples

### Basic conversions
```bash
# CSV → JSON
python transform.py data.csv --to json --pretty

# JSON → SQL (PostgreSQL)
python transform.py data.json --to sql --table users --dialect postgres

# CSV → Markdown table
python transform.py data.csv --to markdown

# NDJSON logs → CSV
python transform.py app.log --to csv

# Pipe from stdin
cat records.ndjson | python transform.py --from ndjson --to csv
```

### Nested JSON
```bash
# Flatten nested objects before converting to CSV
python transform.py api_response.json --to csv --flatten

# Explode array field: one row per item
python transform.py orders.json --to csv --explode items
```

### Schema inference
```bash
# Human-readable column summary
python infer_schema.py data.csv --output summary

# JSON Schema draft-07
python infer_schema.py data.json --output json-schema

# SQL CREATE TABLE
python infer_schema.py data.csv --output sql --table my_table
```

### Large files
```bash
# Stream a big CSV without loading into memory
python transform.py big.csv --to ndjson --stream

# Custom null values for messy data
python transform.py export.csv --to sql --null-values "N/A,#N/A,unknown,-,–"
```

---

## What Claude handles automatically

When this skill is active, Claude:

- **Auto-detects** input format from file extension (`.csv`, `.json`, `.ndjson`, `.yaml`, `.tsv`)
- **Infers types** — integers, floats, booleans, dates, and nulls from string values
- **Handles encoding** — auto-detects UTF-8, UTF-8 BOM, and Latin-1; accepts `--encoding` override
- **Normalises nulls** — empty cells, `NULL`, `N/A`, `n/a`, `none`, `nil`, `NaN`, `-`
- **Picks the right SQL dialect** — SQLite, MySQL, or PostgreSQL type mappings
- **Escapes SQL values** safely — no SQL injection through `'` escaping
- **Streams large files** — CSV and NDJSON output without loading the full dataset

---

## Requirements

- **Python 3.8+** (no install needed — included in macOS, most Linux, and Windows 10+)
- **PyYAML** *(optional)* — `pip install pyyaml` for YAML input or high-fidelity YAML output

---

## transform.py — Full Options

```
usage: transform.py [-h] --to FORMAT [--from FORMAT] [--table NAME]
                    [--dialect sqlite|mysql|postgres] [--batch N]
                    [--delimiter CHAR] [--out-delimiter CHAR] [--no-header]
                    [--null-values LIST] [--flatten] [--sep SEP]
                    [--explode FIELD] [--no-infer] [--stream] [--pretty]
                    [--encoding ENC] [-o FILE]
                    [input]

Key flags:
  --to           Output format: json ndjson csv tsv sql yaml markdown toml
  --table        SQL table name (default: data)
  --dialect      SQL dialect: sqlite mysql postgres (default: sqlite)
  --flatten      Recursively flatten nested JSON objects
  --sep          Separator for flattened key paths (default: __)
  --explode      Expand array field (nested paths like user__tags work): one output row per element
  --null-values  Extra null strings, comma-separated
  --no-infer     Keep all values as strings
  --stream       Write rows as they are read (CSV/TSV/NDJSON output; JSON/YAML input is still read whole)
  --pretty       Pretty-print JSON output
  -o FILE        Write to file instead of stdout
```

## infer_schema.py — Full Options

```
usage: infer_schema.py [-h] [--output json-schema|sql|summary]
                       [--table NAME] [--sample N] [--enum-threshold N]
                       input

Key flags:
  --output          json-schema (default), sql, or summary
  --table           Table name for SQL output
  --sample          Max rows to analyze (default: 1000)
  --enum-threshold  Max unique values to list as enum (default: 20)
```

---

## License

MIT — free to use, modify, and redistribute.

---

*Built as a Claude Code skill by [@bernhardbrugger](https://github.com/bernhardbrugger)*

## Development
```bash
pip install pytest pyyaml
pytest
```
The tests cover type inference, explode/flatten, every writer (TOML output is parsed back with `tomllib` on Python 3.11+) and streaming. A GitHub Actions workflow is prepared in `ci/github-actions-ci.yml`.
