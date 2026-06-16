"""Demo catalog endpoints."""

import csv
import re

from fastapi import APIRouter, HTTPException

from app.deployer import DEMOS_DIR, list_demos, load_manifest, list_scenarios_for_demo

router = APIRouter(prefix="/api/demos", tags=["demos"])

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SAFE_FILE_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,128}$")


@router.get("")
async def get_demos():
    """List all available industry demos."""
    return list_demos()


@router.get("/{demo_id}")
async def get_demo(demo_id: str):
    """Get full details for a specific demo."""
    if not _SAFE_ID.match(demo_id):
        raise HTTPException(status_code=400, detail="Invalid demo_id")
    return load_manifest(demo_id)


@router.get("/{demo_id}/scenarios")
async def get_demo_scenarios(demo_id: str):
    """List deployment scenarios for a demo (from manifest.custom.json + _scenarios/)."""
    if not _SAFE_ID.match(demo_id):
        raise HTTPException(status_code=400, detail="Invalid demo_id")
    return list_scenarios_for_demo(demo_id)


@router.get("/{demo_id}/data/{file_name}/preview")
async def preview_sample_data(
    demo_id: str,
    file_name: str,
):
    """Return a bounded preview (25 rows) of a declared CSV sample dataset."""
    limit = 25
    if not _SAFE_ID.match(demo_id):
        raise HTTPException(status_code=400, detail="Invalid demo_id")
    if not _SAFE_FILE_NAME.match(file_name):
        raise HTTPException(status_code=400, detail="Invalid file_name")

    try:
        manifest = load_manifest(demo_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Demo not found") from None

    sample = next(
        (item for item in manifest.get("sampleData", []) if item.get("fileName") == file_name),
        None,
    )
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample dataset not found")
    if sample.get("format", "").lower() != "csv":
        raise HTTPException(status_code=415, detail="Only CSV sample previews are supported")

    data_path = (DEMOS_DIR / demo_id / "data" / file_name).resolve()
    data_dir = (DEMOS_DIR / demo_id / "data").resolve()
    if data_dir not in data_path.parents or not data_path.exists() or not data_path.is_file():
        raise HTTPException(status_code=404, detail="Sample data file not found")

    rows: list[dict[str, str]] = []
    try:
        with data_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            for index, row in enumerate(reader):
                if index >= limit:
                    break
                rows.append({column: row.get(column, "") for column in columns})
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="Sample data file is not UTF-8 encoded") from None
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse CSV: {exc}") from None

    return {
        "fileName": file_name,
        "columns": columns,
        "rows": rows,
        "shownRows": len(rows),
        "totalRows": sample.get("rows"),
    }
