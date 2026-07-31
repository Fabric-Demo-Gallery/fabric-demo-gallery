"""Deployment usage analytics - permanent JSONL tally + Application Insights events.

Two sinks, both best-effort (analytics must never break a deploy):

1. deployments.jsonl - append-only, one line per deployment lifecycle event,
   never evicted (unlike the job store's 200/user cap). Lives next to the job
   store on the App Service's persistent /home disk. This is the permanent
   source of truth for "how many times has each demo been deployed".

2. Application Insights customEvents - the same events pushed to Azure Monitor
   via the REST ingestion endpoint (no SDK dependency; we already ship httpx).
   Gives portal charts, KQL, alerting, and correlation with other telemetry.
   Enabled only when APPLICATIONINSIGHTS_CONNECTION_STRING is set.

User ids are one-way hashed for the public aggregate endpoint. The sign-in
name (UPN) is ALSO recorded server-side (JSONL + App Insights) so admins can
see who is using the gallery - it is never exposed through /api/stats.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

from app.job_store import PERSIST_PATH as _JOB_STORE_PATH

ANALYTICS_PATH = Path(os.environ.get("ANALYTICS_LOG_PATH", str(_JOB_STORE_PATH.parent / "deployments.jsonl")))

# ── Application Insights connection (optional) ──────────────────────────────
_AI_IKEY: str | None = None
_AI_ENDPOINT: str | None = None
_conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
for part in _conn.split(";"):
    k, _, v = part.partition("=")
    if k.strip().lower() == "instrumentationkey":
        _AI_IKEY = v.strip()
    elif k.strip().lower() == "ingestionendpoint":
        _AI_ENDPOINT = v.strip().rstrip("/")


# Fault-domain classifier for failed deploys - runs server-side because the
# public API never carries raw error text. Distinguishes failures the USER must
# resolve (input conflicts, tenant settings, consent, quota - not product bugs)
# from app/platform failures. Unknown errors default to app-side so real
# problems are never hidden behind a "user error" label.
_USER_FAULT_PATTERNS = [
    "already exists", "choose a different name", "invalid character",  # input
    "feature is not available",  # tenant can't create Fabric items
    "lacks a service principal", "aadsts", "consent", "conditional access",  # tenant auth
    "sufficient scopes",  # stale consent - re-sign-in fixes
    "quota", "not registered", "disallowed by policy", "public network",  # subscription
    "authorizationfailure",  # storage data plane blocked by network policy (SFI)
    "paused", "no active fabric capacity",  # capacity state
    "unauthorized", "sign-in expired",  # session
]


def _classify_fault(error: str) -> str:
    m = error.lower()
    return "user" if any(p in m for p in _USER_FAULT_PATTERNS) else "app"


def _user_hash(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def record_deployment_event(
    event: str,
    *,
    demo_id: str,
    scenario_id: str | None,
    job_id: str,
    user_id: str,
    email: str | None = None,
    duration_s: float | None = None,
    error: str | None = None,
    failed_step: str | None = None,
) -> None:
    """Record a deployment lifecycle event (deploy_started/completed/failed/cancelled)."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "demo_id": demo_id,
        "scenario_id": scenario_id or "standard",
        "job_id": job_id,
        "user": _user_hash(user_id),
    }
    if email:
        rec["email"] = email
    if duration_s is not None:
        rec["duration_s"] = round(duration_s, 1)
    # Failure diagnostics - private sinks only (JSONL + App Insights), never
    # surfaced through the public /api/stats aggregates.
    if error:
        rec["error"] = error[:1000]
    if failed_step:
        rec["failed_step"] = failed_step

    # Sink 1 - append-only JSONL (permanent tally)
    try:
        ANALYTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANALYTICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        logger.warning("Analytics file write failed: %s", e)

    # Sink 2 - Application Insights customEvent (fire-and-forget)
    if _AI_IKEY and _AI_ENDPOINT:
        _fire_app_insights(rec)


# Fire-and-forget App Insights sends: asyncio only holds a WEAK reference to
# tasks, so an unreferenced create_task() can be garbage-collected mid-send and
# the event silently dropped. Keep a strong reference until each task finishes.
_pending_sends: set[asyncio.Task] = set()


def _fire_app_insights(rec: dict) -> None:
    try:
        task = asyncio.get_running_loop().create_task(_send_app_insights(rec))
        _pending_sends.add(task)
        task.add_done_callback(_pending_sends.discard)
    except RuntimeError:
        pass  # no running loop (e.g. tests) - file sink already has it


def record_view_event(demo_id: str) -> None:
    """Record an anonymous demo page view (no identity - views happen pre-sign-in)."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "demo_viewed",
        "demo_id": demo_id,
    }
    try:
        ANALYTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANALYTICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        logger.warning("Analytics file write failed: %s", e)
    if _AI_IKEY and _AI_ENDPOINT:
        _fire_app_insights(rec)


# Raw MSAL/AADSTS error text can theoretically embed a signed-in UPN (e.g.
# AADSTS50020) - redact anything email-shaped and strip control chars before
# it touches a sink. The detail is diagnostics-only and never leaves the
# private sinks (JSONL + App Insights).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_detail(detail: str) -> str:
    return _EMAIL_RE.sub("[redacted]", _CTRL_RE.sub(" ", detail))[:500]


def record_auth_error_event(
    code: str,
    scenario_id: str | None = None,
    detail: str | None = None,
    stage: str | None = None,
) -> None:
    """Record an anonymous sign-in/consent failure (error code only - no identity).
    Makes client-side auth breakage visible in App Insights instead of silent.

    stage="deploy" marks failures that killed a deploy BEFORE the backend was
    ever called (token acquisition in the browser) - recorded as a distinct
    "deploy_auth_failed" event so the AADSTS650052 class of incident (deploy
    dies client-side with zero backend telemetry) is visible. `detail` carries
    the sanitized raw MSAL/AADSTS message for diagnosis."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "deploy_auth_failed" if stage == "deploy" else "auth_error",
        "error": code,
    }
    if scenario_id:
        rec["scenario_id"] = scenario_id
    if detail:
        rec["error_detail"] = _sanitize_detail(detail)
    try:
        ANALYTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANALYTICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        logger.warning("Analytics file write failed: %s", e)
    if _AI_IKEY and _AI_ENDPOINT:
        _fire_app_insights(rec)


async def _send_app_insights(rec: dict) -> None:
    envelope = {
        "name": f"Microsoft.ApplicationInsights.{_AI_IKEY.replace('-', '')}.Event",
        "time": rec["ts"],
        "iKey": _AI_IKEY,
        "data": {
            "baseType": "EventData",
            "baseData": {
                "ver": 2,
                "name": rec["event"],
                "properties": {
                    # Defensive .get - view events carry only demo_id.
                    key: str(rec[key])
                    for key in ("demo_id", "scenario_id", "job_id", "user", "email", "duration_s", "error", "failed_step", "error_detail")
                    if key in rec
                },
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{_AI_ENDPOINT}/v2/track", json=[envelope])
    except Exception as e:
        logger.warning("App Insights send failed (non-fatal): %s", e)


def aggregate_stats(include_detail: bool = False) -> dict:
    """Aggregate the JSONL log into dashboard-ready counts."""
    total_started = 0
    by_demo: Counter = Counter()
    by_scenario: Counter = Counter()
    by_outcome: Counter = Counter()
    by_day: dict[str, int] = defaultdict(int)
    by_hour: dict[int, int] = defaultdict(int)
    by_weekday: dict[int, int] = defaultdict(int)
    users: set[str] = set()
    users_7d: set[str] = set()
    users_30d: set[str] = set()
    durations: list[float] = []
    # Per-demo / per-scenario outcome detail: {key: {started, completed, failed, cancelled, durations}}
    demo_detail: dict[str, dict] = defaultdict(lambda: {"started": 0, "completed": 0, "failed": 0, "cancelled": 0, "durations": []})
    scenario_detail: dict[str, dict] = defaultdict(lambda: {"started": 0, "completed": 0, "failed": 0, "cancelled": 0, "durations": []})
    views_by_demo: Counter = Counter()
    total_views = 0
    recent: list[dict] = []

    now = datetime.now(timezone.utc)

    try:
        if ANALYTICS_PATH.exists():
            with ANALYTICS_PATH.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ev = rec.get("event", "")
                    demo = rec.get("demo_id", "?")
                    scenario = rec.get("scenario_id", "?")
                    ts_raw = rec.get("ts", "")
                    # Page views: count and skip - they'd flood the deployment feed.
                    if ev == "demo_viewed":
                        total_views += 1
                        views_by_demo[demo] += 1
                        continue
                    # Auth failures: diagnostics only (JSONL + App Insights) - keep
                    # them out of the public aggregate/recent feed entirely.
                    if ev in ("auth_error", "deploy_auth_failed"):
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_raw)
                    except ValueError:
                        ts = None
                    if ev == "deploy_started":
                        total_started += 1
                        by_demo[demo] += 1
                        by_scenario[scenario] += 1
                        by_day[ts_raw[:10]] += 1
                        users.add(rec.get("user", "?"))
                        demo_detail[demo]["started"] += 1
                        scenario_detail[scenario]["started"] += 1
                        if ts:
                            by_hour[ts.hour] += 1
                            by_weekday[ts.weekday()] += 1
                            age_days = (now - ts).total_seconds() / 86400
                            if age_days <= 7:
                                users_7d.add(rec.get("user", "?"))
                            if age_days <= 30:
                                users_30d.add(rec.get("user", "?"))
                    elif ev in ("deploy_completed", "deploy_failed", "deploy_cancelled"):
                        outcome = ev.removeprefix("deploy_")
                        by_outcome[outcome] += 1
                        demo_detail[demo][outcome] += 1
                        scenario_detail[scenario][outcome] += 1
                        if "duration_s" in rec:
                            durations.append(rec["duration_s"])
                            demo_detail[demo]["durations"].append(rec["duration_s"])
                            scenario_detail[scenario]["durations"].append(rec["duration_s"])
                    # Public recent-activity feed - deliberately NO email and only a
                    # truncated user hash (enough to see "same person", not who).
                    recent.append({
                        "ts": ts_raw,
                        "event": ev,
                        "demo_id": demo,
                        "scenario_id": scenario,
                        "user": (rec.get("user") or "")[:6],
                        **({"duration_s": rec["duration_s"]} if "duration_s" in rec else {}),
                        # Fault domain ("user" | "app") is classified server-side from
                        # the FULL error text and is safe to expose publicly - it's a
                        # bare label carrying no message content.
                        **({"fault": _classify_fault(str(rec.get("error") or ""))} if ev == "deploy_failed" else {}),
                        # Failure diagnostics - privacy-gated: only for requests that
                        # proved knowledge of STATS_DETAIL_SECRET (the internal dev
                        # dashboard). The public feed never carries error text.
                        **({"error": str(rec["error"])[:200]} if include_detail and ev == "deploy_failed" and rec.get("error") else {}),
                        **({"failed_step": str(rec["failed_step"])[:80]} if include_detail and ev == "deploy_failed" and rec.get("failed_step") else {}),
                    })
    except Exception as e:
        logger.warning("Analytics aggregation failed: %s", e)

    def _percentile(vals: list[float], p: float) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        idx = min(len(s) - 1, max(0, round(p * (len(s) - 1))))
        return s[idx]

    def _detail_out(detail: dict[str, dict]) -> dict:
        out = {}
        for key, d in detail.items():
            finished_k = d["completed"] + d["failed"] + d["cancelled"]
            out[key] = {
                "started": d["started"],
                "completed": d["completed"],
                "failed": d["failed"],
                "cancelled": d["cancelled"],
                "success_rate": round(d["completed"] / finished_k, 3) if finished_k else None,
                "median_duration_s": _percentile(d["durations"], 0.5),
            }
        return dict(sorted(out.items(), key=lambda kv: kv[1]["started"], reverse=True))

    finished = sum(by_outcome.values())
    return {
        "total_deployments": total_started,
        "total_views": total_views,
        "views_by_demo": dict(views_by_demo.most_common()),
        "distinct_users": len(users),
        "distinct_users_7d": len(users_7d),
        "distinct_users_30d": len(users_30d),
        "by_demo": dict(by_demo.most_common()),
        "by_scenario": dict(by_scenario.most_common()),
        "demo_detail": _detail_out(demo_detail),
        "scenario_detail": _detail_out(scenario_detail),
        "outcomes": dict(by_outcome),
        "success_rate": round(by_outcome.get("completed", 0) / finished, 3) if finished else None,
        "median_duration_s": _percentile(durations, 0.5),
        "duration_percentiles_s": {
            "min": _percentile(durations, 0.0),
            "p25": _percentile(durations, 0.25),
            "median": _percentile(durations, 0.5),
            "p75": _percentile(durations, 0.75),
            "p90": _percentile(durations, 0.9),
            "max": _percentile(durations, 1.0),
        },
        "per_day": dict(sorted(by_day.items())),
        "by_hour_utc": {str(h): by_hour.get(h, 0) for h in range(24)},
        "by_weekday": {str(d): by_weekday.get(d, 0) for d in range(7)},  # 0=Mon
        "recent": recent[-30:][::-1],
    }
