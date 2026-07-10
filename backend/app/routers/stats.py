"""Public usage statistics — aggregated deployment counts (no PII)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analytics import aggregate_stats, record_view_event
from app.deployer import list_demos

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats():
    """Aggregate deployment usage: totals, per-demo/scenario counts, outcomes,
    success rate, median duration, and deploys per day. Contains only hashed
    user identifiers aggregated to a distinct count — no personal data."""
    return aggregate_stats()


class ViewEvent(BaseModel):
    demo_id: str


@router.post("/view", status_code=204)
async def record_view(body: ViewEvent):
    """Record an anonymous demo page view. Unauthenticated (views happen before
    sign-in), so the demo id is validated against the catalog to keep junk out
    of the analytics log."""
    valid_ids = {d["id"] for d in list_demos()}
    if body.demo_id not in valid_ids:
        raise HTTPException(status_code=400, detail="Unknown demo id")
    record_view_event(body.demo_id)
