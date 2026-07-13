"""Public usage statistics — aggregated deployment counts (no PII)."""

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analytics import aggregate_stats, record_view_event, record_auth_error_event
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


_AUTH_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SCENARIO_RE = re.compile(r"^[a-z0-9-]{1,64}$")


class AuthErrorEvent(BaseModel):
    code: str
    scenario_id: str | None = None


@router.post("/auth-error", status_code=204)
async def record_auth_error(body: AuthErrorEvent):
    """Record an anonymous sign-in/consent failure code (e.g. AADSTS65001,
    popup_blocked). Unauthenticated — these happen exactly when auth is broken —
    so inputs are strictly pattern-validated to keep junk/PII out of the log."""
    if not _AUTH_CODE_RE.match(body.code):
        raise HTTPException(status_code=400, detail="Invalid error code")
    if body.scenario_id is not None and not _SCENARIO_RE.match(body.scenario_id):
        raise HTTPException(status_code=400, detail="Invalid scenario id")
    record_auth_error_event(body.code, body.scenario_id)
