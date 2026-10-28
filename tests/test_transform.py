import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

SCRIPT = (pathlib.Path(__file__).resolve().parents[1]
          / "skills" / "data-transform" / "scripts" / "transform.py")
spec = importlib.util.spec_from_file_location("transform", SCRIPT)
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

NULLS = frozenset(t._DEFAULT_NULLS.split(","))


def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8")


def strict_json(text):
    """json.loads that rejects NaN / Infinity, which are not valid JSON."""
    def bad(const):
        raise ValueError(f"invalid JSON constant {const}")
    return json.loads(text, parse_constant=bad)


# ── type inference ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("42", 42), ("-7", -7), ("+5", 5), ("0", 0),
    ("41.5", 41.5), ("1e5", 100000.0), ("2.5E-3", 0.0025), (".5", 0.5),
    ("true", True), ("Yes", True), ("off", False),
    ("", None), ("N/A", None), ("null", None),
])
def test_infer_typed_values(raw, expected):
    got = t._infer(raw, NULLS)
    assert got == expected and type(got) is type(expected)


@pytest.mark.parametrize("raw", [
    "01234",      # ZIP code / ID: must not become 1234 or 1234.0
    "007", "007.5", "00",
    "1_000", "12_34",   # Python's float() would accept underscores
    "nan", "inf", "-inf", "Infinity",   # not valid JSON numbers
    "٣",          # non-ASCII digit
    "1e", "1.2.3", "--5", "12abc", "+",
])
def test_infer_keeps_ambiguous_values_as_text(raw):
    assert t._infer(raw, NULLS) == raw


def test_csv_to_json_is_valid_json_and_keeps_ids(tmp_path):
    f = tmp_path / "z.csv"
    f.write_text("zip,code,x,y\n01234,1_000,nan,Infinity\n", encoding="utf-8")
    r = run(str(f), "--to", "json")
    assert r.returncode == 0, r.stderr
    assert strict_json(r.stdout) == [{"zip": "01234", "code": "1_000", "x": "nan", "y": "Infinity"}]


# ── explode / flatten ──────────────────────────────────────────────────────

def test_explode_top_level_dict_items():
    rows = [{"id": 1, "items": [{"sku": "a"}, {"sku": "b"}]}]
    assert list(t.explode(iter(rows), "items")) == [
        {"id": 1, "items__sku": "a"}, {"id": 1, "items__sku": "b"}]


def test_explode_top_level_scalars():
    assert list(t.explode(iter([{"id": 1, "tags": ["x", "y"]}]), "tags")) == [
        {"id": 1, "tags": "x"}, {"id": 1, "tags": "y"}]


def test_explode_empty_array_keeps_the_row():
    assert list(t.explode(iter([{"id": 1, "tags": []}]), "tags")) == [{"id": 1, "tags": None}]


def test_explode_nested_path_with_separator_or_dot():
    row = {"id": 1, "user": {"name": "A", "tags": ["x", "y"]}}
    for field in ("user__tags", "user.tags"):
        out = list(t.explode(iter([row]), field))
        assert [r["user"]["tags"] for r in out] == ["x", "y"]
        assert all(r["user"]["name"] == "A" and r["id"] == 1 for r in out)
    assert row["user"]["tags"] == ["x", "y"]        # input rows are not mutated


def test_explode_unknown_field_passes_rows_through():
    rows = [{"id": 1}]
    assert list(t.explode(iter(rows), "nope")) == rows


def test_flatten_and_explode_work_together_on_the_command_line(tmp_path):
    f = tmp_path / "n.json"
    f.write_text(json.dumps([{"id": 1, "user": {"name": "Anna", "tags": ["a", "b"]}}]), encoding="utf-8")
    r = run(str(f), "--to", "csv", "--flatten", "--explode", "user__tags")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["id,user__name,user__tags", "1,Anna,a", "1,Anna,b"]


def test_flatten_stringifies_remaining_arrays():
    assert t.flatten({"a": {"b": [1, 2]}, "c": 1}) == {"a__b": "[1, 2]", "c": 1}


# ── writers ────────────────────────────────────────────────────────────────

def test_csv_booleans_are_lowercase_like_all_other_writers():
    out = t.write_csv([{"ok": True, "no": False, "n": None, "obj": {"a": 1}}])
    assert out.splitlines() == ["ok,no,n,obj", 'true,false,,"{""a"": 1}"']


def test_toml_is_valid_for_nested_values_and_awkward_strings():
    tomllib = pytest.importorskip("tomllib")
    rows = [{
        "id": 1,
        "user": {"name": "Anna", "tags": ["a", "b"], "gone": None},
        "note": 'line1\nline2 "quoted" back\\slash\ttab',
        "ok": True, "ratio": 0.5, "none": None,
        'key "with" quotes': "x",
    }]
    doc = tomllib.loads(t.write_toml(rows))
    rec = doc["record"][0]
    assert rec["user"] == {"name": "Anna", "tags": ["a", "b"]}
    assert rec["note"] == rows[0]["note"]
    assert rec["ok"] is True and rec["ratio"] == 0.5 and "none" not in rec
    assert rec['key "with" quotes'] == "x"


def test_toml_special_floats():
    tomllib = pytest.importorskip("tomllib")
    doc = tomllib.loads(t.write_toml([{"a": float("inf"), "b": float("-inf")}]))
    assert doc["record"][0]["a"] == float("inf") and doc["record"][0]["b"] == float("-inf")


def test_sql_escapes_quotes_and_picks_types():
    out = t.write_sql([{"id": 1, "name": "O'Brien", "score": 2.5, "ok": True, "d": "2024-01-31"}],
                      table="users", dialect="postgres")
    assert 'CREATE TABLE IF NOT EXISTS "users"' in out
    assert '"id" INTEGER' in out and '"score" DOUBLE PRECISION' in out
    assert '"ok" BOOLEAN' in out and '"d" DATE' in out
    assert "'O''Brien'" in out


def test_sql_mysql_quoting_and_batching():
    rows = [{"a": i} for i in range(5)]
    out = t.write_sql(rows, table="t", dialect="mysql", batch=2)
    assert "`t`" in out and out.count("INSERT INTO") == 3


def test_markdown_escapes_pipes_and_newlines():
    out = t.write_markdown([{"a": "x|y", "b": "l1\nl2", "c": None, "d": True}])
    assert out.splitlines()[2] == "| x\\|y | l1 l2 |  | true |"


def test_yaml_fallback_quotes_risky_strings(monkeypatch):
    monkeypatch.setattr(t, "_HAS_YAML", False)
    out = t.write_yaml([{"a": "x: y", "b": True, "c": None, "d": "plain"}])
    assert '  a: "x: y"' in out and "  b: true" in out and "  c: null" in out and "  d: plain" in out


def test_yaml_roundtrip_with_pyyaml():
    yaml = pytest.importorskip("yaml")
    rows = [{"id": 1, "n": {"a": [1, 2]}, "s": "x: y"}]
    assert yaml.safe_load(t.write_yaml(rows)) == rows


# ── command line ───────────────────────────────────────────────────────────

def test_stdin_ndjson_to_csv():
    r = run("--from", "ndjson", "--to", "csv", stdin='{"a":1,"b":"x"}\n{"a":2,"b":"y"}\n')
    assert r.stdout.splitlines() == ["a,b", "1,x", "2,y"]


def test_stream_output_matches_normal_output(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("id,name\n1,Anna\n2,\"Bob, Jr.\"\n", encoding="utf-8")
    for fmt in ("csv", "ndjson"):
        normal = run(str(f), "--to", fmt)
        streamed = run(str(f), "--to", fmt, "--stream")
        assert streamed.returncode == 0, streamed.stderr
        assert streamed.stdout.strip() == normal.stdout.strip()


def test_stream_warns_when_later_rows_have_new_columns():
    data = '{"a":1}\n{"a":2,"b":3}\n'
    streamed = run("--from", "ndjson", "--to", "csv", "--stream", stdin=data)
    assert streamed.stdout.splitlines() == ["a", "1", "2"]
    assert "dropped: b" in streamed.stderr
    assert run("--from", "ndjson", "--to", "csv", stdin=data).stdout.splitlines()[0] == "a,b"


def test_output_file_option(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("id\n1\n", encoding="utf-8")
    out = tmp_path / "o.json"
    r = run(str(f), "--to", "json", "-o", str(out))
    assert r.returncode == 0 and strict_json(out.read_text(encoding="utf-8")) == [{"id": 1}]


def test_infer_schema_script_runs(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("id,name,joined\n1,Anna,2024-01-05\n2,Bob,2024-02-10\n", encoding="utf-8")
    schema = SCRIPT.with_name("infer_schema.py")
    r = subprocess.run([sys.executable, str(schema), str(f), "--output", "summary"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "joined" in r.stdout


def test_infer_schema_agrees_with_transform_on_ids(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("zip,qty,price\n01234,5,1.5\n04711,7,2\n", encoding="utf-8")
    schema = SCRIPT.with_name("infer_schema.py")
    r = subprocess.run([sys.executable, str(schema), str(f), "--output", "sql", "--table", "t"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert '"zip" TEXT' in r.stdout or "zip TEXT" in r.stdout or "`zip` TEXT" in r.stdout
    assert "qty INTEGER" in r.stdout.replace('"', "").replace("`", "")
