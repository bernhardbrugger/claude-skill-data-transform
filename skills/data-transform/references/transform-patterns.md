# Transform Patterns & Recipes

Ready-to-run command sequences for the most common data-transform tasks.
Read this file when the user's request maps to one of these patterns.

---

## 1. Normalize a JSON API Response → SQL seed file

**Scenario**: You called a REST API, got a JSON array of objects, and want to seed a database.

```bash
# Step 1: Inspect what you have
python scripts/infer_schema.py response.json --output summary

# Step 2: Preview the SQL (SQLite)
python scripts/transform.py response.json --to sql --table products

# Step 3: PostgreSQL-ready seed file
python scripts/transform.py response.json \
  --to sql --table products --dialect postgres --batch 1000 \
  -o seed.sql
```

If the response is nested (e.g. each record has an embedded `address` object):
```bash
python scripts/transform.py response.json \
  --to sql --table products --flatten --sep "__" --dialect postgres
```

---

## 2. Flatten Nested JSON → CSV

**Scenario**: JSON objects have several nesting levels; you need a flat CSV for Excel or Pandas.

```bash
# Default: nested keys joined with "__"
python scripts/transform.py nested.json --to csv --flatten

# Dot-path keys: user.address.city
python scripts/transform.py nested.json --to csv --flatten --sep .

# With explicit output file
python scripts/transform.py nested.json --to csv --flatten -o flat.csv
```

**Before** (one row):
```json
{"id": 1, "user": {"name": "Alice", "address": {"city": "NY", "zip": "10001"}}}
```
**After** columns: `id`, `user__name`, `user__address__city`, `user__address__zip`

---

## 3. Explode an Array Field (one row per element)

**Scenario**: Each JSON record has an array (e.g. `items` in an order), and you want a relational table.

```bash
# Explode the "items" array
python scripts/transform.py orders.json --to csv --explode items

# Explode then convert to SQL
python scripts/transform.py orders.json --to sql --explode items --table order_lines
```

**Before** (one row):
```json
{"order_id": 42, "items": [{"sku": "A1", "qty": 2}, {"sku": "B3", "qty": 1}]}
```
**After** (two rows): `order_id=42, items__sku=A1, items__qty=2` and `order_id=42, items__sku=B3, items__qty=1`

---

## 4. Convert Structured Logs (NDJSON) → CSV / Markdown

**Scenario**: App logs are in JSON Lines format; you want to analyse them in a spreadsheet or paste into a report.

```bash
# NDJSON → CSV
python scripts/transform.py app.log --to csv -o logs.csv

# Preview as markdown table (first 20 rows via head)
python scripts/transform.py app.log --to markdown | head -22

# Pipe directly from a running process
tail -f app.log | python scripts/transform.py --from ndjson --to csv
```

---

## 5. European CSV (semicolon-delimited) → JSON

**Scenario**: An Excel export uses `;` as delimiter and numbers like `1.234,56`.

```bash
# Use semicolon delimiter
python scripts/transform.py report.csv --to json --delimiter ";" --pretty

# Keep values as strings if the number format is non-standard
python scripts/transform.py report.csv --to json --delimiter ";" --no-infer --pretty
```

---

## 6. CSV with Custom Null Representations → SQL

**Scenario**: Your CSV uses `#N/A`, `unknown`, and `–` for missing values.

```bash
python scripts/transform.py data.csv \
  --to sql --table survey \
  --null-values "null,NULL,N/A,#N/A,unknown,–,-,n/a" \
  --dialect postgres
```

---

## 7. Large File Streaming (> 100 MB)

**Scenario**: The file is too large to load entirely into memory.

```bash
# CSV → NDJSON (streamed)
python scripts/transform.py huge.csv --to ndjson --stream -o huge.ndjson

# CSV → CSV re-delimited (streamed)
python scripts/transform.py huge.csv --to csv --delimiter ";" --out-delimiter "," --stream

# NDJSON → CSV (streamed)
python scripts/transform.py huge.ndjson --to csv --stream -o out.csv
```

Note: `--stream` only works for NDJSON and CSV output formats. For SQL, JSON, YAML, or Markdown output, the entire dataset is loaded into memory regardless.

---

## 8. Infer Schema → CREATE TABLE

**Scenario**: You have a CSV with unknown column types and need to create a table before bulk-loading.

```bash
# Human overview first
python scripts/infer_schema.py data.csv --output summary

# SQLite DDL
python scripts/infer_schema.py data.csv --output sql --table my_table

# PostgreSQL DDL
python scripts/infer_schema.py data.csv --output sql --table my_table \
  | sed 's/REAL/DOUBLE PRECISION/g; s/INTEGER/BIGINT/g'

# JSON Schema (for API validation)
python scripts/infer_schema.py data.json --output json-schema > schema.json
```

---

## 9. Convert CSV → Markdown Table (for docs / reports)

**Scenario**: You want to paste data into a README, Confluence page, or pull-request description.

```bash
# Print markdown table to stdout
python scripts/transform.py data.csv --to markdown

# Save to file
python scripts/transform.py data.csv --to markdown -o table.md

# Preview just the first N rows: pass a slice via stdin
head -11 data.csv | python scripts/transform.py --to markdown
```

---

## 10. Batch Convert a Directory of CSVs → JSON

**Scenario**: A folder of daily report CSVs all need to become JSON for an API upload.

```bash
for f in reports/*.csv; do
  base="${f%.csv}"
  python scripts/transform.py "$f" --to json --pretty -o "${base}.json"
  echo "✓ ${f}"
done
```

---

## 11. Join / Merge Two CSV Files (manual approach)

`transform.py` does not perform joins natively. The recommended approach:

```bash
# Step 1: Convert both to JSON
python scripts/transform.py users.csv    --to json -o users.json
python scripts/transform.py orders.csv   --to json -o orders.json

# Step 2: Claude performs the join in Python (write a small script)
# Then convert the merged result back:
python scripts/transform.py merged.json --to csv
```

Or load both into SQLite and use SQL:
```bash
python scripts/transform.py users.csv  --to sql --table users  -o setup.sql
python scripts/transform.py orders.csv --to sql --table orders >> setup.sql
# Then run in sqlite3: SELECT * FROM users JOIN orders ON ...
```

---

## 12. No-Header CSV → JSON with Named Columns

**Scenario**: The CSV has no header row; you know what the columns mean.

```bash
# Step 1: Convert with auto-generated names col0, col1, …
python scripts/transform.py raw.csv --to json --no-header --pretty

# The output has keys "col0", "col1", etc.
# Step 2: Use jq or a small Python script to rename them,
# or pass the column mapping in natural language and Claude handles it.
```

---

## 13. YAML Config File → Markdown Documentation Table

**Scenario**: A YAML file has a list of configuration entries; you want a readable table.

```bash
python scripts/transform.py config.yaml --to markdown
```

Requires `pip install pyyaml` for YAML input.

---

## 14. Pivot / Reshape Data

`transform.py` does not natively pivot (wide ↔ long). For pivot operations, the best approach is:

```bash
# Export to CSV, then let Claude write a pandas one-liner:
python scripts/transform.py data.json --to csv -o data.csv
# Claude: "pivot this CSV so that column X becomes rows..."
```

Alternatively, load into SQLite and pivot with SQL aggregation.

---

## Decision Guide: Which Script for Which Job?

| Task | Script | Key flags |
|------|--------|-----------|
| Format conversion | `transform.py` | `--to FORMAT` |
| Flatten nested JSON | `transform.py` | `--flatten [--sep]` |
| Explode array field | `transform.py` | `--explode FIELD` |
| Large file (>100 MB) | `transform.py` | `--stream` (ndjson/csv out) |
| Understand column types | `infer_schema.py` | `--output summary` |
| Generate CREATE TABLE | `infer_schema.py` | `--output sql` |
| Validate against schema | `infer_schema.py` | `--output json-schema` → use with ajv / jsonschema |
| Custom null values | `transform.py` | `--null-values "…"` |
| Keep everything as string | `transform.py` | `--no-infer` |
