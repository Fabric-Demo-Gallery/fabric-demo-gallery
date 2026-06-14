#!/usr/bin/env python3
"""Validate every demos/<demo>/mirroring.json against its real CSV data.

Run before deploying any mirroring scenario. Catches the failure modes that would
otherwise only surface mid-deploy (wrong column name, unbounded/oversized primary
key type, a live-change target that does not exist, etc).

Usage:
    python tools/validate_mirroring_specs.py            # validate all specs
    python tools/validate_mirroring_specs.py retail-sales healthcare   # subset

Exits non-zero if any spec fails.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMOS = REPO / "demos"

# Primary-key types that mirroring rejects or that blow the clustered-index key limit.
UNSUPPORTED_PK_TYPES = ("DATETIME2(7)", "DATETIMEOFFSET(7)", "TIME(7)", "SQL_VARIANT")
VALID_MUTATE_KINDS = ("number", "flag", "status")


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def pk_byte_size_ok(sqltype: str) -> tuple[bool, str]:
    """A PK string column must be bounded and small enough for the index key limit
    (<= ~900 bytes). VARCHAR(n) is n bytes; NVARCHAR(n) is 2n bytes."""
    up = sqltype.upper().replace(" ", "")
    m = re.match(r"^(N?VARCHAR)\((\d+|MAX)\)$", up)
    if not m:
        # non-string types (INT, DATE, DATETIME2(3), DECIMAL...) are fine as PKs
        if up in UNSUPPORTED_PK_TYPES:
            return False, f"{sqltype} is not a valid primary-key type for mirroring"
        if up in ("VARCHAR", "NVARCHAR", "CHAR", "NCHAR"):
            return False, f"{sqltype} must specify a length, e.g. VARCHAR(20)"
        return True, ""
    kind, n = m.group(1), m.group(2)
    if n == "MAX":
        return False, f"{sqltype} cannot be a primary key (use a bounded length)"
    nbytes = int(n) * (2 if kind == "NVARCHAR" else 1)
    if nbytes > 900:
        return False, f"{sqltype} is too large for a primary key ({nbytes} bytes > 900)"
    return True, ""


def validate_spec(demo: str) -> list[str]:
    errors: list[str] = []
    spec_path = DEMOS / demo / "mirroring.json"
    data_dir = DEMOS / demo / "data"
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"cannot parse mirroring.json: {e}"]

    if not spec.get("mirroredDbName"):
        errors.append("missing 'mirroredDbName'")
    if not isinstance(spec.get("rowCap"), int) or spec.get("rowCap", 0) <= 0:
        errors.append("'rowCap' must be a positive integer")

    tables = spec.get("tables") or []
    if not tables:
        errors.append("'tables' is empty")
    table_names = {t.get("name") for t in tables}
    headers: dict[str, list[str]] = {}

    for t in tables:
        name = t.get("name", "?")
        csvfile = t.get("sourceCsv", "")
        csv_path = data_dir / csvfile
        if not csv_path.exists():
            errors.append(f"[{name}] sourceCsv '{csvfile}' not found in {data_dir}")
            continue
        cols = csv_header(csv_path)
        headers[name] = cols
        colset = set(cols)

        pk = t.get("primaryKey") or []
        if not pk:
            errors.append(f"[{name}] missing 'primaryKey'")
        ctypes = t.get("columnTypes") or {}
        for c in pk:
            if c not in colset:
                errors.append(f"[{name}] primary-key column '{c}' is not in {csvfile} ({cols})")
            if c not in ctypes:
                errors.append(f"[{name}] primary-key column '{c}' must have an explicit type in columnTypes")
            else:
                ok, why = pk_byte_size_ok(ctypes[c])
                if not ok:
                    errors.append(f"[{name}] primary-key column '{c}': {why}")
        for c in ctypes:
            if c not in colset:
                errors.append(f"[{name}] columnTypes column '{c}' is not in {csvfile} ({cols})")

    # explore
    explore = spec.get("explore") or {}
    if not explore.get("sql"):
        errors.append("missing 'explore.sql'")
    else:
        # Match m_<table> temp views, but only at an identifier boundary so column
        # names like room_nights don't masquerade as a view "m_nights".
        for view in re.findall(r"(?<![A-Za-z0-9_])m_([a-zA-Z0-9_]+)", explore["sql"]):
            if view not in table_names:
                errors.append(f"explore.sql references m_{view} but '{view}' is not a table in the spec")

    # liveChange
    lc = spec.get("liveChange") or {}
    lct = lc.get("table")
    if lct not in table_names:
        errors.append(f"liveChange.table '{lct}' is not one of the spec tables")
    else:
        cols = set(headers.get(lct, []))
        for field in ("keyColumn", "mutateColumn"):
            col = lc.get(field)
            if not col:
                errors.append(f"liveChange missing '{field}'")
            elif col not in cols:
                errors.append(f"liveChange.{field} '{col}' is not in {lct}'s CSV")
        disp = lc.get("displayColumn")
        if disp and disp not in cols:
            errors.append(f"liveChange.displayColumn '{disp}' is not in {lct}'s CSV")
        kind = lc.get("mutateKind")
        if kind not in VALID_MUTATE_KINDS:
            errors.append(f"liveChange.mutateKind '{kind}' must be one of {VALID_MUTATE_KINDS}")
        if kind == "status" and "statusTo" not in lc:
            errors.append("liveChange.mutateKind 'status' requires 'statusTo'")
    return errors


def check_scenario_wiring() -> list[str]:
    """Cross-check mirroring wiring across every demo so a misconfiguration is
    caught here instead of mid-deploy:
      - a demo that OFFERS the external-data-integration scenario must ship a mirroring.json
      - a demo that ships a mirroring.json must OFFER the scenario (else it's unreachable)
    """
    scenario_id = "external-data-integration"
    errors: list[str] = []
    for demo_dir in sorted(p for p in DEMOS.iterdir() if p.is_dir() and p.name != "_scenarios"):
        custom = demo_dir / "manifest.custom.json"
        offers = False
        if custom.exists():
            try:
                data = json.loads(custom.read_text(encoding="utf-8"))
                offers = any(s.get("id") == scenario_id for s in data.get("scenarios", []))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{demo_dir.name}: cannot parse manifest.custom.json: {e}")
                continue
        has_spec = (demo_dir / "mirroring.json").exists()
        if offers and not has_spec:
            errors.append(f"{demo_dir.name}: offers '{scenario_id}' but has no mirroring.json")
        if has_spec and not offers:
            errors.append(f"{demo_dir.name}: has mirroring.json but does not offer '{scenario_id}'")
    return errors


def main() -> int:
    requested = sys.argv[1:]
    demos = requested or sorted(
        p.parent.name for p in DEMOS.glob("*/mirroring.json")
    )
    if not demos:
        print("No mirroring.json specs found.")
        return 0
    failed = 0
    for demo in demos:
        if not (DEMOS / demo / "mirroring.json").exists():
            print(f"FAIL {demo}: no mirroring.json")
            failed += 1
            continue
        errs = validate_spec(demo)
        if errs:
            failed += 1
            print(f"FAIL {demo}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   {demo}")
    print(f"\n{len(demos) - failed}/{len(demos)} specs valid")

    # Global wiring check (only when validating the full set, not a subset).
    if not requested:
        wiring_errs = check_scenario_wiring()
        if wiring_errs:
            failed += 1
            print("\nScenario wiring problems:")
            for e in wiring_errs:
                print(f"  - {e}")
        else:
            print("Scenario wiring OK (specs match offered scenarios)")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
