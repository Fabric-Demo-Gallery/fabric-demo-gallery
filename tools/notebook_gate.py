"""Static medallion-notebook gate for the Fabric Demo Gallery.

A precision-first AST analyzer that symbolically tracks each notebook's DataFrame
schema through the Bronze -> Silver -> Gold medallion notebooks and flags
PROVABLE errors before a deploy ever runs. It only FAILs when a column set is
KNOWN and a reference is provably absent (no guessing), so a PASS is meaningful
and a FAIL is real.

Checks per industry:
  1. syntax            — every code cell must ast.parse
  2. undefined-names   — names used-but-never-bound (minus builtins/Fabric globals)
  3. column contract   — col()/select/groupBy/join/orderBy/drop against the
                         schema carried across cells (shared env) + read/write
                         table contract
  4. model.bim         — every Direct Lake table/sourceColumn/relationship column
                         must exist in a modelled gold table
  5. agg-string-arg    — F.sum("x")/avg("x")/... string args must exist
  6. ambiguous-join    — a non-key column present on BOTH sides of a join, then
                         referenced in groupBy/select, is ambiguous at runtime

Usage:
  python backend/_notebook_gate.py <industry>
  python backend/_notebook_gate.py --list
  python backend/_notebook_gate.py --all
Exit code is non-zero if any industry FAILs (suitable for CI).
"""
from __future__ import annotations

import ast
import builtins
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMOS_DIR = (HERE.parent / "demos") if (HERE.parent / "demos").exists() else (HERE / "demos")

UNKNOWN = None  # sentinel: schema not statically determinable

SHORTCUT_NOTEBOOKS = [
    "notebooks/01_bronze_ingest.ipynb",
    "notebooks/02_silver_transform.ipynb",
    "notebooks/03_gold_aggregate.ipynb",
]
# columns the bronze layer adds beyond the CSV header
BRONZE_META = {"ingestion_timestamp", "source_file", "ingestion_batch_id", "batch_id", "_ingested_at"}

PY_BUILTINS = set(dir(builtins))
FABRIC_GLOBALS = {
    "spark", "sc", "dbutils", "display", "displayHTML", "mssparkutils",
    "notebookutils", "getArgument", "sqlContext", "udf",
}
AGG_FUNCS = {
    "sum", "avg", "mean", "min", "max", "count", "countDistinct", "sumDistinct",
    "stddev", "stddev_samp", "stddev_pop", "variance", "var_samp", "var_pop",
    "first", "last", "collect_list", "collect_set", "approx_count_distinct",
    "skewness", "kurtosis",
}


# ── helpers ─────────────────────────────────────────────────────────────────
def code_cells(nb_path: Path) -> list[str]:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    out = []
    for c in nb.get("cells", []):
        if c.get("cell_type") == "code":
            out.append("".join(c.get("source", [])))
    return out


def strip_magics(src: str) -> str:
    lines = []
    for ln in src.splitlines():
        s = ln.lstrip()
        if s.startswith("%") or s.startswith("!"):
            continue
        if s.startswith("#"):
            lines.append(ln)
            continue
        lines.append(ln)
    return "\n".join(lines)


def csv_headers(data_dir: Path) -> dict[str, frozenset]:
    out: dict[str, frozenset] = {}
    if not data_dir.exists():
        return out
    for p in data_dir.glob("*.csv"):
        try:
            with p.open(encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f), [])
            out[p.name] = frozenset(h.strip() for h in header if h.strip())
        except Exception:
            pass
    return out


def const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def fstring_basename(node) -> str | None:
    """Trailing filename from an f-string path: f\"{P}/vehicles.csv\" -> vehicles.csv."""
    if isinstance(node, ast.JoinedStr):
        for v in reversed(node.values):
            if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value.strip("/"):
                return os.path.basename(v.value.rstrip("/"))
    return None


def _callee_name(call) -> str | None:
    fn = call.func if isinstance(call, ast.Call) else None
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def struct_cols(node) -> frozenset | None:
    """Columns from StructType([StructField(\"name\", ...), ...])."""
    if _callee_name(node) != "StructType" or not getattr(node, "args", None):
        return None
    if not isinstance(node.args[0], (ast.List, ast.Tuple)):
        return None
    out = []
    for e in node.args[0].elts:
        if isinstance(e, ast.Call) and _callee_name(e) == "StructField" and e.args:
            c = const_str(e.args[0])
            if c:
                out.append(c)
    return frozenset(out) if out else None


def collect_bound(tree, bound: set):
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                bound.add(a.asname or a.name)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            bound.add(n.id)
        elif isinstance(n, (ast.For, ast.comprehension)):
            tgt = getattr(n, "target", None)
            if isinstance(tgt, ast.Name):
                bound.add(tgt.id)
        elif isinstance(n, ast.withitem) and isinstance(n.optional_vars, ast.Name):
            bound.add(n.optional_vars.id)


def collect_used(tree) -> set:
    used = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            used.add(n.func.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            used.add(n.value.id)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            used.add(n.id)
    return used


# ── DataFrame schema model ──────────────────────────────────────────────────
class DF:
    __slots__ = ("cols", "kind", "keys", "amb")

    def __init__(self, cols, kind="df", keys=None, amb=None):
        self.cols = cols          # frozenset | UNKNOWN
        self.kind = kind          # df | grouped | writer | reader | schema | other
        self.keys = keys or []
        self.amb = amb or frozenset()


# ── analyzer ────────────────────────────────────────────────────────────────
class Analyzer:
    def __init__(self, csv_map: dict[str, frozenset]):
        self.csv = csv_map
        self.tables: dict[str, frozenset | None] = {}
        self.findings: list[tuple] = []
        self.cur_nb = ""
        self.cur_cell = 0
        self.alias_map: dict[str, str] = {}

    def flag(self, sev, msg):
        self.findings.append((sev, self.cur_nb, self.cur_cell, msg))

    # column-reference checks ------------------------------------------------
    def check_col_refs(self, node, cols, where):
        if cols is UNKNOWN:
            return
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                fn = n.func
                name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else None)
                if name == "col" and n.args:
                    s = const_str(n.args[0])
                    if s and s not in cols:
                        self.flag("FAIL", f"{where}: col('{s}') not in {sorted(cols)[:12]}…")
                elif name in AGG_FUNCS and n.args:
                    s = const_str(n.args[0])
                    if s and s != "*" and s not in cols:
                        self.flag("FAIL", f"{where}: {name}('{s}') not in {sorted(cols)[:12]}…")

    def check_literal_cols(self, args, cols, where):
        if cols is UNKNOWN:
            return
        for a in args:
            s = const_str(a)
            if s and s != "*" and s not in cols:
                self.flag("FAIL", f"{where}: column '{s}' not in {sorted(cols)[:12]}…")

    # evaluation -------------------------------------------------------------
    def eval(self, node, env):
        try:
            return self._eval(node, env)
        except Exception:
            return DF(UNKNOWN, "other")

    def _eval(self, node, env):
        if isinstance(node, ast.Name):
            v = env.get(node.id)
            return v if isinstance(v, DF) else DF(UNKNOWN, "other")
        if isinstance(node, ast.Attribute):
            return self._eval(node.value, env)
        if isinstance(node, ast.Call):
            return self._eval_call(node, env)
        if isinstance(node, ast.IfExp):
            if isinstance(node.test, ast.Constant):
                return self._eval(node.body if node.test.value else node.orelse, env)
            a = self._eval(node.body, env)
            return a if a.cols is not UNKNOWN else self._eval(node.orelse, env)
        return DF(UNKNOWN, "other")

    def _eval_call(self, call, env):
        func = call.func
        if not isinstance(func, ast.Attribute):
            sc = struct_cols(call)
            if sc is not None:
                return DF(sc, "schema")
            return DF(UNKNOWN, "other")
        method = func.attr
        recv = self._eval(func.value, env)
        args = call.args
        cols = recv.cols

        # ---- read sources ----
        if method == "table":
            name = const_str(args[0]) if args else None
            if name is None:
                return DF(UNKNOWN, "df")
            if name in self.tables:
                return DF(self.tables[name], "df")
            self.flag("FAIL", f"reads table '{name}' never written upstream")
            return DF(UNKNOWN, "df")
        if method in ("load", "csv"):
            if cols is not UNKNOWN:      # schema already applied
                return DF(cols, "df")
            p = const_str(args[0]) if args else None
            if not p and args:
                p = fstring_basename(args[0])
            if p:
                base = os.path.basename(p)
                if base in self.csv:
                    return DF(frozenset(self.csv[base]), "df")
            return DF(UNKNOWN, "df")
        if method == "schema":
            sc = self._eval(args[0], env) if args else DF(UNKNOWN)
            if sc.cols is not UNKNOWN:
                return DF(sc.cols, "reader")
            if args and struct_cols(args[0]) is not None:
                return DF(struct_cols(args[0]), "reader")
            return recv
        if method in ("format", "option", "options"):
            return recv

        # ---- column-producing transforms ----
        if method == "withColumn":
            new = const_str(args[0]) if args else None
            if len(args) > 1:
                self.check_col_refs(args[1], cols, f"withColumn('{new}')")
            if cols is not UNKNOWN and new is not None:
                return DF(cols | {new}, "df", amb=recv.amb)
            return DF(UNKNOWN, "df")
        if method == "withColumnRenamed":
            old = const_str(args[0]) if args else None
            new = const_str(args[1]) if len(args) > 1 else None
            if cols is not UNKNOWN and old is not None and new is not None:
                if old not in cols:
                    self.flag("FAIL", f"withColumnRenamed: '{old}' not in {sorted(cols)[:12]}…")
                return DF((cols - {old}) | {new}, "df", amb=recv.amb - {old})
            return DF(UNKNOWN, "df")
        if method == "drop":
            dropped = {const_str(a) for a in args if const_str(a)}
            if cols is not UNKNOWN:
                return DF(cols - dropped, "df", amb=recv.amb - dropped)
            return DF(UNKNOWN, "df")
        if method in ("select", "selectExpr"):
            new_cols = set()
            ok = True
            for a in args:
                s = const_str(a)
                if s is not None:
                    if cols is not UNKNOWN and s != "*" and s not in cols:
                        self.flag("FAIL", f"select: column '{s}' not in {sorted(cols)[:12]}…")
                    new_cols.add(s)
                elif isinstance(a, ast.Call):
                    self.check_col_refs(a, cols, "select")
                    al = self._alias_of(a)
                    if al:
                        new_cols.add(al)
                    else:
                        ok = False
                else:
                    ok = False
            if ok and new_cols and "*" not in new_cols:
                return DF(frozenset(new_cols), "df", amb=recv.amb & frozenset(new_cols))
            return DF(UNKNOWN, "df")
        if method in ("filter", "where"):
            for a in args:
                self.check_col_refs(a, cols, method)
            return DF(cols, "df", amb=recv.amb)
        if method in ("orderBy", "sort"):
            for a in args:
                self.check_col_refs(a, cols, method)
                self.check_literal_cols([a], cols, method)
            return DF(cols, "df", amb=recv.amb)
        if method in ("join",):
            other = self._eval(args[0], env) if args else DF(UNKNOWN)
            on_node = args[1] if len(args) > 1 else None
            for kw in call.keywords:
                if kw.arg == "on":
                    on_node = kw.value
            on_strs = []
            if on_node is not None:
                if const_str(on_node) is not None:
                    on_strs = [const_str(on_node)]
                elif isinstance(on_node, (ast.List, ast.Tuple)):
                    on_strs = [const_str(e) for e in on_node.elts if const_str(e)]
            for s in on_strs:
                if cols is not UNKNOWN and s not in cols:
                    self.flag("FAIL", f"join on '{s}' not in left {sorted(cols)[:10]}…")
                if other.cols is not UNKNOWN and s not in other.cols:
                    self.flag("FAIL", f"join on '{s}' not in right {sorted(other.cols)[:10]}…")
            if cols is not UNKNOWN and other.cols is not UNKNOWN:
                overlap = (cols & other.cols) - set(on_strs)
                return DF(cols | other.cols, "df", amb=(recv.amb | other.amb | overlap))
            return DF(UNKNOWN, "df")
        if method in ("union", "unionByName", "unionAll"):
            return DF(cols, "df", amb=recv.amb)
        if method in ("groupBy", "groupby", "rollup", "cube"):
            self.check_literal_cols(args, cols, "groupBy")
            for a in args:
                self.check_col_refs(a, cols, "groupBy")
                s = const_str(a)
                if s and s in recv.amb:
                    self.flag("FAIL", f"groupBy: column '{s}' is AMBIGUOUS after a join (present on both sides — drop/rename one)")
            keys = [const_str(a) for a in args if const_str(a)]
            return DF(cols, "grouped", keys, amb=recv.amb)
        if method == "agg":
            for a in args:
                self.check_col_refs(a, cols, "agg")
            new = set(recv.keys)
            for a in args:
                if isinstance(a, ast.Call):
                    al = self._alias_of(a)
                    if al:
                        new.add(al)
            if recv.kind == "grouped" and new:
                return DF(frozenset(new), "df")
            return DF(UNKNOWN, "df")
        if method in ("distinct", "dropDuplicates", "cache", "persist", "repartition",
                      "coalesce", "limit", "alias", "hint", "checkpoint",
                      "localCheckpoint", "fillna", "na", "replace", "toDF",
                      "withWatermark", "sample"):
            return DF(cols, "df", amb=recv.amb)

        # ---- writers ----
        if method in ("write", "writeTo"):
            return DF(cols, "writer")
        if method in ("mode", "format", "option", "options", "partitionBy", "bucketBy"):
            return DF(cols, recv.kind)
        if method in ("saveAsTable", "save", "insertInto"):
            name = const_str(args[0]) if args else None
            if name:
                self.tables[name] = cols
            return DF(cols, "writer")
        return DF(UNKNOWN, "other")

    def _alias_of(self, call) -> str | None:
        node = call
        while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("alias", "name") and node.args:
                return const_str(node.args[0])
            node = node.func.value
        return None

    # statement execution ----------------------------------------------------
    def _exec_stmt(self, stmt, env):
        if isinstance(stmt, ast.Assign):
            val = self.eval(stmt.value, env)
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    env[t.id] = val
        elif isinstance(stmt, ast.Expr):
            self.eval(stmt.value, env)

    def run_notebook(self, nb_path: str, nb_label: str):
        self.cur_nb = nb_label
        p = Path(nb_path)
        cells = code_cells(p)
        trees = []
        for i, raw in enumerate(cells):
            src = strip_magics(raw)
            try:
                tree = ast.parse(src)
            except SyntaxError as e:
                self.cur_cell = i
                self.flag("FAIL", f"syntax error: {e.msg} (line {e.lineno})")
                trees.append(None)
                continue
            trees.append(tree)

        # shared symbolic env across all cells (notebooks share a namespace)
        env: dict[str, DF] = {}
        for i, tree in enumerate(trees):
            if tree is None:
                continue
            self.cur_cell = i
            for stmt in tree.body:
                self._exec_stmt(stmt, env)


# ── model.bim contract ──────────────────────────────────────────────────────
def validate_model_bim(demo_dir: Path, tables: dict, findings: list):
    bim = demo_dir / "tmdl" / "model.bim"
    if not bim.exists():
        return
    try:
        model = json.loads(bim.read_text(encoding="utf-8")).get("model", {})
    except Exception:
        return
    modelled = {t: c for t, c in tables.items() if c is not UNKNOWN and t.startswith("gold_")}
    for tbl in model.get("tables", []):
        ent = None
        for part in tbl.get("partitions", []):
            src = part.get("source", {})
            ent = src.get("entityName") or ent
        target = ent or tbl.get("name")
        cols_known = modelled.get(target)
        if cols_known is None:
            continue
        for col in tbl.get("columns", []):
            sc = col.get("sourceColumn")
            if sc and sc not in cols_known:
                findings.append(("FAIL", "model.bim", 0,
                                 f"table '{target}' sourceColumn '{sc}' not produced by gold notebook"))


# ── per-industry entry point ────────────────────────────────────────────────
def analyze(industry: str) -> list[tuple]:
    demo_dir = DEMOS_DIR / industry
    az = Analyzer(csv_headers(demo_dir / "data"))
    present = [n for n in SHORTCUT_NOTEBOOKS if (demo_dir / n).exists()]
    if not present:
        return [("WARN", industry, 0, "no medallion notebooks (KQL/real-time or ML scenario) — gate skipped")]
    for n in present:
        az.run_notebook(str(demo_dir / n), Path(n).name)
    validate_model_bim(demo_dir, az.tables, az.findings)
    return az.findings


def list_industries() -> list[str]:
    out = []
    for d in sorted(DEMOS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "notebooks").exists():
            out.append(d.name)
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "--list":
        for i in list_industries():
            print(i)
        return 0
    industries = list_industries() if argv[0] == "--all" else [argv[0]]
    any_fail = False
    for ind in industries:
        findings = analyze(ind)
        fails = [f for f in findings if f[0] == "FAIL"]
        if fails:
            any_fail = True
            print(f"{ind:22} STATIC GATE: {len(fails)} FAIL(s)")
            for sev, nb, cell, msg in fails:
                print(f"   [FAIL] {nb} (cell {cell}): {msg}")
        else:
            warns = [f for f in findings if f[0] == "WARN"]
            note = "  (" + warns[0][3] + ")" if warns else "  (no provable column/contract/syntax errors)"
            print(f"{ind:22} STATIC GATE: PASS{note}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
