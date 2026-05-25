"""Demo catalog endpoints."""

import re

from fastapi import APIRouter, HTTPException

from app.deployer import list_demos, load_manifest, list_scenarios_for_demo

router = APIRouter(prefix="/api/demos", tags=["demos"])

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


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
