#!/usr/bin/env python3
"""
transform.py — Universal data format converter
Part of the claude-skill-data-transform skill.

Supported conversions (from → to):
  CSV / TSV  → json, ndjson, sql, yaml, markdown, toml, csv, tsv
  JSON       → csv, ndjson, sql, yaml, markdown, toml
  NDJSON     → csv, json, sql, yaml, markdown
  YAML       → csv, json, ndjson, sql, markdown

Requirements: Python 3.8+  (stdlib only)
Optional:     pip install pyyaml   # for YAML input/output

Usage:
  python transform.py data.csv --to json
  python transform.py data.csv --to json --pretty
  python transform.py data.json --to sql --table users --dialect postgres
  python transform.py data.csv --to markdown
  python transform.py nested.json --to csv --flatten --sep .
  python transform.py orders.json --to csv --explode items
  python transform.py data.csv --to yaml --null-values "N/A,#N/A,unknown"
  cat records.ndjson | python transform.py --from ndjson --to csv
  python transform.py big.csv --to ndjson --stream
  python transform.py data.csv --to sql -o seed.sql
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from typing import Any, Dict, Iterator, List, Optional

# ── Optional dependencies ──────────────────────────────────────────────────

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

# ── Types & constants ─────────────────────────────────────────────────────

Row = Dict[str, Any]

_DEFAULT_NULLS = "null,NULL,N/A,n/a,NA,na,None,none,-,—,nil,NaN"

_DATE_RE = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),    # 2024-01-31
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),    # 01/31/2024
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),    # 2024/01/31
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),    # 01-31-2024
]

# SQL type promotion: index position is the "rank" (higher = more general)
_TYPE_RANK = {"boolean": 0, "integer": 1, "float": 2, "date": 3, "text": 4}

_SQL_TYPES = {
    "boolean": {"sqlite": "INTEGER",  "mysql": "TINYINT(1)", "postgres": "BOOLEAN"},
    "integer": {"sqlite": "INTEGER",  "mysql": "INT",         "postgres": "INTEGER"},
    "float":   {"sqlite": "REAL",     "mysql": "DOUBLE",      "postgres": "DOUBLE PRECISION"},
    "date":    {"sqlite": "TEXT",     "mysql": "DATE",         "postgres": "DATE"},
    "text":    {"sqlite": "TEXT",     "mysql": "TEXT",         "postgres": "TEXT"},
}


# ── Utilities ─────────────────────────────────────────────────────────────

def _detect_encoding(path: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                f.read(8192)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _detect_format(path: Optional[str]) -> str:
    if not path or path == "-":
        return "csv"
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {
        "csv": "csv", "tsv": "tsv", "tab": "tsv",
        "json": "json",
        "ndjson": "ndjson", "jsonl": "ndjson",
        "yaml": "yaml", "yml": "yaml",
    }.get(ext, "csv")


def _infer(s: str, nulls: frozenset) -> Any:
    """Parse a CSV string into the most specific Python type."""
    if s in nulls or s == "":
        return None
    lo = s.lower()
    if lo in ("true", "yes", "on"):
        return True
    if lo in ("false", "no", "off"):
        return False
    # Integer — reject leading-zero strings like "007"
    try:
        iv = int(s)
        if s in (str(iv), f"+{iv}", f"-{abs(iv)}" if iv < 0 else None):
            return iv
    except (ValueError, TypeError):
        pass
    # Float (includes scientific notation like 1e5)
    try:
        return float(s)
    except ValueError:
        pass
    return s


# ── Readers ───────────────────────────────────────────────────────────────

def _open(source, encoding: str, mode: str = "r", newline: str = ""):
    if isinstance(source, (str, bytes, os.PathLike)):
        return open(source, mode, encoding=encoding, newline=newline), True
    return source, False


def read_csv(source, delimiter: str = ",", has_header: bool = True,
             nulls: frozenset = frozenset(), infer: bool = True,
             encoding: str = "utf-8") -> Iterator[Row]:
    fh, owned = _open(source, encoding, newline="")
    try:
        if has_header:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                yield {k: (_infer(v, nulls) if infer else v)
                       for k, v in row.items()}
        else:
            for row in csv.reader(fh, delimiter=delimiter):
                d = {f"col{i}": v for i, v in enumerate(row)}
                yield {k: (_infer(v, nulls) if infer else v) for k, v in d.items()}
    finally:
        if owned:
            fh.close()


def read_json(source, encoding: str = "utf-8") -> Iterator[Row]:
    fh, owned = _open(source, encoding)
    try:
        data = json.load(fh)
    finally:
        if owned:
            fh.close()
    if isinstance(data, list):
        yield from data
    elif isinstance(data, dict):
        yield data
    else:
        raise ValueError(f"JSON root must be array or object, got {type(data).__name__}")


def read_ndjson(source, encoding: str = "utf-8") -> Iterator[Row]:
    fh, owned = _open(source, encoding)
    try:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
    finally:
        if owned:
            fh.close()


def read_yaml(source, encoding: str = "utf-8") -> Iterator[Row]:
    if not _HAS_YAML:
        sys.exit("YAML input requires PyYAML:  pip install pyyaml")
    fh, owned = _open(source, encoding)
    try:
        data = _yaml.safe_load(fh)
    finally:
        if owned:
            fh.close()
    if isinstance(data, list):
        yield from data
    elif isinstance(data, dict):
        yield data


# ── Transformations ───────────────────────────────────────────────────────

def flatten(row: Any, sep: str = "__", prefix: str = "") -> Row:
    """Recursively flatten nested dicts. Arrays are JSON-stringified."""
    if not isinstance(row, dict):
        return {prefix: row} if prefix else {"value": row}
    out: Row = {}
    for k, v in row.items():
        key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, sep, key))
        elif isinstance(v, list):
            out[key] = json.dumps(v, ensure_ascii=False)
        else:
            out[key] = v
    return out


def explode(rows: Iterator[Row], field: str) -> Iterator[Row]:
    """Yield one row per element in the named array field."""
    for row in rows:
        val = row.get(field)
        if isinstance(val, list):
            base = {k: v for k, v in row.items() if k != field}
            for item in val:
                new = dict(base)
                if isinstance(item, dict):
                    new.update({f"{field}__{k}": v for k, v in item.items()})
                else:
                    new[field] = item
                yield new
        else:
            yield row


# ── Writers ───────────────────────────────────────────────────────────────

def _all_keys(rows: List[Row]) -> List[str]:
    """Union of all keys preserving first-seen insertion order."""
    seen: Dict[str, None] = {}
    for row in rows:
        seen.update(dict.fromkeys(row))
    return list(seen)


def write_json(rows: List[Row], pretty: bool = False) -> str:
    return json.dumps(rows, indent=2 if pretty else None,
                      ensure_ascii=False, default=str)


def write_ndjson(rows: List[Row]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows)


def write_csv(rows: List[Row], delimiter: str = ",") -> str:
    if not rows:
        return ""
    keys = _all_keys(rows)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, delimiter=delimiter,
                       extrasaction="ignore", restval="", lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({
            k: ("" if v is None
                else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list))
                else v)
            for k, v in row.items()
        })
    return buf.getvalue()


def _sql_col_types(rows: List[Row], dialect: str) -> Dict[str, str]:
    ranks: Dict[str, int] = {}
    for row in rows:
        for col, val in row.items():
            if val is None:
                continue
            if isinstance(val, bool):
                t = "boolean"
            elif isinstance(val, int):
                t = "integer"
            elif isinstance(val, float):
                t = "float"
            else:
                s = str(val)
                t = "date" if any(p.match(s) for p in _DATE_RE) else "text"
            r = _TYPE_RANK.get(t, 4)
            ranks[col] = max(ranks.get(col, 0), r)
    type_names = list(_TYPE_RANK.keys())
    return {
        col: _SQL_TYPES[type_names[rank]][dialect]
        for col, rank in ranks.items()
    }


def write_sql(rows: List[Row], table: str = "data",
              dialect: str = "sqlite", batch: int = 500) -> str:
    if not rows:
        return f"-- No rows to insert into {table}\n"
    keys = _all_keys(rows)
    types = _sql_col_types(rows, dialect)

    q = (lambda n: f"`{n}`") if dialect == "mysql" else (lambda n: f'"{n}"')

    def val(x: Any) -> str:
        if x is None:
            return "NULL"
        if isinstance(x, bool):
            return "1" if x else "0"
        if isinstance(x, (int, float)):
            return str(x)
        s = str(x).replace("'", "''")
        if dialect == "mysql":
            s = s.replace("\\", "\\\\")
        return f"'{s}'"

    col_defs = ",\n  ".join(f"{q(c)} {types.get(c, 'TEXT')}" for c in keys)
    out = [f"CREATE TABLE IF NOT EXISTS {q(table)} (\n  {col_defs}\n);\n"]

    for i in range(0, len(rows), batch):
        chunk = rows[i: i + batch]
        cols  = ", ".join(q(c) for c in keys)
        vals  = ",\n  ".join(
            "(" + ", ".join(val(r.get(c)) for c in keys) + ")"
            for r in chunk
        )
        out.append(f"\nINSERT INTO {q(table)} ({cols}) VALUES\n  {vals};")

    return "\n".join(out) + "\n"


def write_markdown(rows: List[Row]) -> str:
    if not rows:
        return "_No data_\n"
    keys = _all_keys(rows)

    def cell(x: Any) -> str:
        if x is None:
            return ""
        if isinstance(x, bool):
            return "true" if x else "false"
        if isinstance(x, (dict, list)):
            return json.dumps(x, ensure_ascii=False)
        return str(x).replace("|", "\\|").replace("\n", " ").replace("\r", "")

    header = "| " + " | ".join(str(k) for k in keys) + " |"
    sep    = "| " + " | ".join("---" for _ in keys)   + " |"
    body   = ["| " + " | ".join(cell(r.get(k)) for k in keys) + " |" for r in rows]
    return "\n".join([header, sep] + body) + "\n"


def write_yaml(rows: List[Row]) -> str:
    if _HAS_YAML:
        return _yaml.dump(rows, allow_unicode=True,
                          default_flow_style=False, sort_keys=False)
    # Minimal stdlib fallback (flat dicts only; install PyYAML for full support)
    lines = []
    _NEEDS_QUOTE = set(':#{}&*!|>\'"%@`')
    for row in rows:
        lines.append("-")
        for k, v in row.items():
            if v is None:
                lines.append(f"  {k}: null")
            elif isinstance(v, bool):
                lines.append(f"  {k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"  {k}: {v}")
            elif isinstance(v, (dict, list)):
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                s = str(v)
                if any(c in s for c in _NEEDS_QUOTE) or s[:1] in "-?" or "\n" in s:
                    lines.append(f"  {k}: {json.dumps(s)}")
                else:
                    lines.append(f"  {k}: {s}")
    return "\n".join(lines) + "\n"


def write_toml(rows: List[Row]) -> str:
    """Emit rows as TOML array of tables ([[record]])."""
    lines = []
    for row in rows:
        lines.append("[[record]]")
        for k, v in row.items():
            safe_k = k.replace('"', '\\"')
            if v is None:
                continue  # TOML 1.0 has no null
            elif isinstance(v, bool):
                lines.append(f'"{safe_k}" = {"true" if v else "false"}')
            elif isinstance(v, int):
                lines.append(f'"{safe_k}" = {v}')
            elif isinstance(v, float):
                lines.append(f'"{safe_k}" = {v}')
            elif isinstance(v, (dict, list)):
                lines.append(f'"{safe_k}" = {json.dumps(v, ensure_ascii=False)}')
            else:
                s = str(v).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'"{safe_k}" = "{s}"')
        lines.append("")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transform.py",
        description="Convert data between CSV, JSON, SQL, YAML, Markdown, TOML, NDJSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  transform.py data.csv --to json --pretty
  transform.py data.json --to sql --table users --dialect postgres
  transform.py data.csv --to markdown
  transform.py nested.json --to csv --flatten --sep .
  transform.py orders.json --to csv --explode items
  transform.py data.csv --to yaml --null-values "N/A,#N/A,unknown"
  cat records.ndjson | transform.py --from ndjson --to csv
  transform.py big.csv --to ndjson --stream
  transform.py data.csv --to sql --batch 1000 -o seed.sql
        """,
    )
    p.add_argument("input", nargs="?", default="-",
                   help="Input file path (default: stdin)")
    p.add_argument("--to", required=True,
                   choices=["json","ndjson","csv","tsv","sql","yaml","markdown","md","toml"],
                   help="Output format")
    p.add_argument("--from", dest="from_fmt",
                   choices=["csv","tsv","json","ndjson","yaml"],
                   help="Force input format (auto-detected from extension otherwise)")
    p.add_argument("--table",    default="data",
                   help="SQL table name (default: data)")
    p.add_argument("--dialect",  default="sqlite",
                   choices=["sqlite","mysql","postgres"],
                   help="SQL dialect (default: sqlite)")
    p.add_argument("--batch",    type=int, default=500,
                   help="Rows per SQL INSERT statement (default: 500)")
    p.add_argument("--delimiter", default=",",
                   help="Input CSV field delimiter (default: ,)")
    p.add_argument("--out-delimiter", default=",",
                   help="Output CSV field delimiter (default: ,)")
    p.add_argument("--no-header", action="store_true",
                   help="Input CSV has no header row (columns named col0, col1, …)")
    p.add_argument("--null-values", default=_DEFAULT_NULLS,
                   help="Comma-separated list of strings to treat as NULL")
    p.add_argument("--flatten", action="store_true",
                   help="Recursively flatten nested JSON objects")
    p.add_argument("--sep", default="__",
                   help="Key-path separator when flattening (default: __)")
    p.add_argument("--explode", metavar="FIELD",
                   help="Expand an array field: one output row per element")
    p.add_argument("--no-infer", action="store_true",
                   help="Keep all values as strings; skip type inference")
    p.add_argument("--stream", action="store_true",
                   help="Stream output without loading entire file into memory")
    p.add_argument("--pretty", action="store_true",
                   help="Pretty-print JSON output with 2-space indent")
    p.add_argument("--encoding", default=None,
                   help="Force input encoding (default: auto-detect UTF-8 / Latin-1)")
    p.add_argument("-o", "--output", default=None,
                   help="Write output to this file instead of stdout")
    return p


def main() -> None:
    # Ensure UTF-8 output on Windows (avoids cp1252 encoding errors)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = _build_parser().parse_args()

    # ── Resolve source & encoding
    src = None if args.input == "-" else args.input
    enc = args.encoding or ((_detect_encoding(src)) if src else "utf-8")

    from_fmt  = args.from_fmt or _detect_format(src)
    to_fmt    = {"md": "markdown"}.get(args.to, args.to)
    out_delim = "\t" if args.to == "tsv" else args.out_delimiter

    nulls  = frozenset(args.null_values.split(","))
    infer  = not args.no_infer
    source = sys.stdin if src is None else src

    # ── Read
    if from_fmt in ("csv", "tsv"):
        delim = "\t" if from_fmt == "tsv" else args.delimiter
        rows_iter: Iterator[Row] = read_csv(
            source, delimiter=delim,
            has_header=not args.no_header,
            nulls=nulls, infer=infer, encoding=enc,
        )
    elif from_fmt == "json":
        rows_iter = read_json(source, encoding=enc)
    elif from_fmt == "ndjson":
        rows_iter = read_ndjson(source, encoding=enc)
    elif from_fmt == "yaml":
        rows_iter = read_yaml(source, encoding=enc)
    else:
        sys.exit(f"Unsupported input format: {from_fmt!r}")

    # ── Transform
    if args.flatten:
        rows_iter = (flatten(r, sep=args.sep) for r in rows_iter)
    if args.explode:
        rows_iter = explode(rows_iter, args.explode)

    # ── Write
    if args.stream and to_fmt in ("ndjson", "csv", "tsv"):
        # True streaming path — never materialises the whole dataset
        if to_fmt == "ndjson":
            result = "\n".join(
                json.dumps(r, ensure_ascii=False, default=str) for r in rows_iter
            )
        else:
            buf    = io.StringIO()
            writer = None
            for row in rows_iter:
                if writer is None:
                    writer = csv.DictWriter(
                        buf, fieldnames=list(row.keys()),
                        delimiter=out_delim, extrasaction="ignore",
                        restval="", lineterminator="\n",
                    )
                    writer.writeheader()
                writer.writerow({
                    k: ("" if v is None
                        else json.dumps(v) if isinstance(v, (dict, list))
                        else v)
                    for k, v in row.items()
                })
            result = buf.getvalue()
    else:
        rows: List[Row] = list(rows_iter)
        if to_fmt == "json":
            result = write_json(rows, pretty=args.pretty)
        elif to_fmt == "ndjson":
            result = write_ndjson(rows)
        elif to_fmt in ("csv", "tsv"):
            result = write_csv(rows, delimiter=out_delim)
        elif to_fmt == "sql":
            result = write_sql(rows, table=args.table,
                               dialect=args.dialect, batch=args.batch)
        elif to_fmt == "markdown":
            result = write_markdown(rows)
        elif to_fmt == "yaml":
            result = write_yaml(rows)
        elif to_fmt == "toml":
            result = write_toml(rows)
        else:
            sys.exit(f"Unsupported output format: {to_fmt!r}")

    # ── Emit
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"✓  Written {len(result):,} chars → {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(result)
        if result and not result.endswith("\n"):
            sys.stdout.write("\n")


if __name__ == "__main__":
    main()
