#!/usr/bin/env python3
"""
infer_schema.py — Schema inference from data files
Part of the claude-skill-data-transform skill.

Analyzes CSV, JSON, or NDJSON files and outputs one of:
  json-schema  (default)  JSON Schema draft-07
  sql                     CREATE TABLE DDL
  summary                 Human-readable column stats

Usage:
  python infer_schema.py data.csv
  python infer_schema.py data.json --output sql --table users
  python infer_schema.py data.csv --output summary
  python infer_schema.py large.csv --sample 2000 --enum-threshold 30

Requirements: Python 3.8+  (stdlib only)
"""

import argparse
import csv
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Constants ─────────────────────────────────────────────────────────────

_NULL_VALS = frozenset([
    "", "null", "NULL", "N/A", "n/a", "NA", "na",
    "None", "none", "-", "—", "nil", "NaN",
])

_DATE_RE = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),
]

# Numbers: no leading zeros, ASCII digits only, no nan/inf (kept in sync with transform.py)
_INT_RE = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)$", re.ASCII)
_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:0|[1-9][0-9]*)\.[0-9]*|\.[0-9]+|(?:0|[1-9][0-9]*)(?=[eE]))(?:[eE][+-]?[0-9]+)?$",
    re.ASCII,
)

# Type promotion order: higher index = more general
_PROMOTE = ["null", "boolean", "integer", "number", "string"]

_SQL_MAP = {
    "null":    "TEXT",
    "boolean": "BOOLEAN",
    "integer": "INTEGER",
    "number":  "REAL",
    "string":  "TEXT",
}


# ── Type inference ────────────────────────────────────────────────────────

def _classify(val: Any) -> str:
    """Return the JSON Schema primitive type of a value."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "number"
    if isinstance(val, (dict, list)):
        return "string"
    s = str(val)
    if s in _NULL_VALS:
        return "null"
    lo = s.lower()
    if lo in ("true", "false", "yes", "no", "on", "off"):
        return "boolean"
    # Same strict number syntax as transform.py: "01234" (ZIP codes, IDs), "1_000", "nan",
    # "inf" and non-ASCII digits are text, not numbers.
    if _INT_RE.match(s):
        return "integer"
    if _FLOAT_RE.match(s):
        return "number"
    # Dates stay as "string" (JSON Schema uses format: date)
    return "string"


def _promote(a: str, b: str) -> str:
    ia = _PROMOTE.index(a) if a in _PROMOTE else len(_PROMOTE) - 1
    ib = _PROMOTE.index(b) if b in _PROMOTE else len(_PROMOTE) - 1
    return _PROMOTE[max(ia, ib)]


# ── Per-column statistics ─────────────────────────────────────────────────

class ColStats:
    __slots__ = ("count", "null_count", "_type", "uniques",
                 "overflowed", "min_len", "max_len", "samples")

    def __init__(self):
        self.count      : int           = 0
        self.null_count : int           = 0
        self._type      : str           = "null"
        self.uniques    : Set[str]      = set()
        self.overflowed : bool          = False
        self.min_len    : Optional[int] = None
        self.max_len    : Optional[int] = None
        self.samples    : List[Any]     = []

    def observe(self, val: Any, enum_cap: int) -> None:
        self.count += 1
        t = _classify(val)
        if t == "null":
            self.null_count += 1
            return
        self._type = _promote(self._type, t)
        s = str(val)
        ln = len(s)
        self.min_len = ln if self.min_len is None else min(self.min_len, ln)
        self.max_len = ln if self.max_len is None else max(self.max_len, ln)
        if len(self.samples) < 5:
            self.samples.append(val)
        if not self.overflowed:
            self.uniques.add(s)
            if len(self.uniques) > enum_cap * 3:
                self.overflowed = True

    @property
    def inferred_type(self) -> str:
        return self._type if self._type != "null" else "string"

    @property
    def nullable(self) -> bool:
        return self.null_count > 0

    def enum_candidates(self, cap: int) -> Optional[List[str]]:
        if self.overflowed or len(self.uniques) > cap:
            return None
        return sorted(self.uniques)

    @property
    def fill_rate(self) -> float:
        if self.count == 0:
            return 0.0
        return (self.count - self.null_count) / self.count


# ── Readers ───────────────────────────────────────────────────────────────

def _sniff_encoding(path: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                f.read(4096)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def load_rows(path: str, sample: int) -> Tuple[List[Dict], int]:
    """Read up to `sample` rows; return (rows, total_count)."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")

    if ext in ("csv", "tsv"):
        enc   = _sniff_encoding(path)
        delim = "\t" if ext == "tsv" else ","
        rows, total = [], 0
        with open(path, encoding=enc, newline="") as f:
            for row in csv.DictReader(f, delimiter=delim):
                total += 1
                if len(rows) < sample:
                    rows.append(dict(row))
        return rows, total

    if ext == "json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[:sample], len(data)
        return ([data], 1) if isinstance(data, dict) else ([], 0)

    if ext in ("ndjson", "jsonl"):
        rows, total = [], 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    total += 1
                    if len(rows) < sample:
                        rows.append(json.loads(s))
        return rows, total

    # Unknown extension — try CSV as fallback
    enc = _sniff_encoding(path)
    rows, total = [], 0
    with open(path, encoding=enc, errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            if len(rows) < sample:
                rows.append(dict(row))
    return rows, total


# ── Output formatters ─────────────────────────────────────────────────────

def to_json_schema(stats: Dict[str, ColStats], enum_cap: int) -> dict:
    props: Dict[str, Any] = {}
    required: List[str]   = []
    for col, s in stats.items():
        t    = s.inferred_type
        prop: Dict[str, Any] = {}
        if s.nullable:
            prop["type"] = [t, "null"]
        else:
            prop["type"] = t
            required.append(col)
        if t == "string" and s.max_len:
            prop["maxLength"] = s.max_len
        enums = s.enum_candidates(enum_cap)
        if enums and t in ("string", "integer", "boolean"):
            prop["enum"] = enums
        props[col] = prop

    schema: Dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": props,
    }
    if required:
        schema["required"] = required
    return schema


def to_sql_ddl(stats: Dict[str, ColStats], table: str) -> str:
    defs = []
    for col, s in stats.items():
        t      = _SQL_MAP.get(s.inferred_type, "TEXT")
        notnull = " NOT NULL" if not s.nullable else ""
        safe   = col.replace('"', '""')
        defs.append(f'  "{safe}" {t}{notnull}')
    return f'CREATE TABLE "{table}" (\n' + ",\n".join(defs) + "\n);"


def to_summary(stats: Dict[str, ColStats], total: int,
               enum_cap: int, path: str) -> str:
    fname = os.path.basename(path)
    w1, w2, w3, w4 = 30, 10, 8, 10
    lines = [
        f"  File    : {fname}",
        f"  Rows    : {total:,}",
        f"  Columns : {len(stats)}",
        "",
        f"  {'Column':<{w1}} {'Type':<{w2}} {'Fill%':<{w3}} {'Unique':<{w4}} Samples / Enum",
        "  " + "-" * 80,
    ]
    for col, s in stats.items():
        t      = s.inferred_type
        fill   = f"{s.fill_rate * 100:.0f}%"
        unique = f">{len(s.uniques)}" if s.overflowed else str(len(s.uniques))
        enums  = s.enum_candidates(enum_cap)
        if enums and len(enums) <= 8:
            detail = "enum: " + " | ".join(str(e) for e in enums[:8])
        else:
            detail = ", ".join(repr(v) for v in s.samples[:3])
        col_d = (col[:w1 - 1] + "…") if len(col) > w1 else col
        lines.append(f"  {col_d:<{w1}} {t:<{w2}} {fill:<{w3}} {unique:<{w4}} {detail}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    # Ensure UTF-8 output on Windows (avoids cp1252 encoding errors)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="infer_schema.py",
        description="Infer schema from CSV, JSON, or NDJSON data files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  infer_schema.py data.csv
  infer_schema.py data.json --output sql --table orders
  infer_schema.py data.csv --output summary
  infer_schema.py large.csv --sample 5000 --enum-threshold 50
        """,
    )
    p.add_argument("input",
                   help="Data file to analyze (CSV, TSV, JSON, NDJSON)")
    p.add_argument("--output", "-o", default="json-schema",
                   choices=["json-schema", "sql", "summary"],
                   help="Output format (default: json-schema)")
    p.add_argument("--table", default="data",
                   help="Table name for SQL output (default: data)")
    p.add_argument("--sample", type=int, default=1000,
                   help="Max rows to analyze for inference (default: 1000)")
    p.add_argument("--enum-threshold", type=int, default=20,
                   help="Max unique values before a column stops being enum (default: 20)")
    args = p.parse_args()

    if not os.path.isfile(args.input):
        sys.exit(f"File not found: {args.input!r}")

    rows, total = load_rows(args.input, args.sample)
    if not rows:
        sys.exit("No rows found in input file.")

    stats: Dict[str, ColStats] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for col, val in row.items():
            if col not in stats:
                stats[col] = ColStats()
            stats[col].observe(val, args.enum_threshold)

    if not stats:
        sys.exit("No columns detected.")

    if args.output == "json-schema":
        schema = to_json_schema(stats, args.enum_threshold)
        print(json.dumps(schema, indent=2, ensure_ascii=False))

    elif args.output == "sql":
        print(to_sql_ddl(stats, args.table))

    elif args.output == "summary":
        print(to_summary(stats, total, args.enum_threshold, args.input))


if __name__ == "__main__":
    main()
