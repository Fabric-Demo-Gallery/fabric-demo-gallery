"""Public usage statistics — aggregated deployment counts (no PII)."""

from fastapi import APIRouter

from app.analytics import aggregate_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats():
    """Aggregate deployment usage: totals, per-demo/scenario counts, outcomes,
    success rate, median duration, and deploys per day. Contains only hashed
    user identifiers aggregated to a distinct count — no personal data."""
    return aggregate_stats()
