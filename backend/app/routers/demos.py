"""Demo catalog endpoints."""

from fastapi import APIRouter

from app.deployer import list_demos, load_manifest

router = APIRouter(prefix="/api/demos", tags=["demos"])


@router.get("")
async def get_demos():
    """List all available industry demos."""
    return list_demos()


@router.get("/{demo_id}")
async def get_demo(demo_id: str):
    """Get full details for a specific demo."""
    return load_manifest(demo_id)
