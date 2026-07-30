"""Public usage statistics - aggregated deployment counts (no PII)."""

import os
import re
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.analytics import aggregate_stats, record_view_event, record_auth_error_event
from app.deployer import list_demos

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats(x_stats_detail: str | None = Header(default=None)):
    """Aggregate deployment usage: totals, per-demo/scenario counts, outcomes,
    success rate, median duration, and deploys per day. Contains only hashed
    user identifiers aggregated to a distinct count - no personal data.

    Failure error strings are privacy-gated: included only when the request
    carries the X-Stats-Detail header matching the STATS_DETAIL_SECRET app
    setting (sent only by the internal dev dashboard build). The public
    response never contains error text."""
    secret = os.environ.get("STATS_DETAIL_SECRET", "")
    include_detail = bool(
        secret and x_stats_detail and secrets.compare_digest(x_stats_detail, secret)
    )
    return aggregate_stats(include_detail=include_detail)


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
_AUTH_STAGES = {"deploy"}


class AuthErrorEvent(BaseModel):
    code: str
    scenario_id: str | None = None
    # Raw MSAL/AADSTS error text for diagnosis - sanitized (control chars,
    # email-shaped tokens) and truncated server-side; private sinks only.
    detail: str | None = None
    # "deploy" = the failure killed a deploy before the backend was called;
    # recorded as a distinct deploy_auth_failed event.
    stage: str | None = None


@router.post("/auth-error", status_code=204)
async def record_auth_error(body: AuthErrorEvent):
    """Record an anonymous sign-in/consent failure code (e.g. AADSTS65001,
    popup_blocked). Unauthenticated - these happen exactly when auth is broken -
    so inputs are strictly pattern-validated to keep junk/PII out of the log."""
    if not _AUTH_CODE_RE.match(body.code):
        raise HTTPException(status_code=400, detail="Invalid error code")
    if body.scenario_id is not None and not _SCENARIO_RE.match(body.scenario_id):
        raise HTTPException(status_code=400, detail="Invalid scenario id")
    if body.stage is not None and body.stage not in _AUTH_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    if body.detail is not None and len(body.detail) > 2000:
        raise HTTPException(status_code=400, detail="Detail too long")
    record_auth_error_event(body.code, body.scenario_id, body.detail, body.stage)
