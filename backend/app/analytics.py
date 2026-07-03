"""Deployment usage analytics — permanent JSONL tally + Application Insights events.

Two sinks, both best-effort (analytics must never break a deploy):

1. deployments.jsonl — append-only, one line per deployment lifecycle event,
   never evicted (unlike the job store's 200/user cap). Lives next to the job
   store on the App Service's persistent /home disk. This is the permanent
   source of truth for "how many times has each demo been deployed".

2. Application Insights customEvents — the same events pushed to Azure Monitor
   via the REST ingestion endpoint (no SDK dependency; we already ship httpx).
   Gives portal charts, KQL, alerting, and correlation with other telemetry.
   Enabled only when APPLICATIONINSIGHTS_CONNECTION_STRING is set.

User ids are one-way hashed — usage analytics needs distinct-user counts, not
identities.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
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


def _user_hash(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def record_deployment_event(
    event: str,
    *,
    demo_id: str,
    scenario_id: str | None,
    job_id: str,
    user_id: str,
    duration_s: float | None = None,
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
    if duration_s is not None:
        rec["duration_s"] = round(duration_s, 1)

    # Sink 1 — append-only JSONL (permanent tally)
    try:
        ANALYTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ANALYTICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        logger.warning("Analytics file write failed: %s", e)

    # Sink 2 — Application Insights customEvent (fire-and-forget)
    if _AI_IKEY and _AI_ENDPOINT:
        try:
            asyncio.get_running_loop().create_task(_send_app_insights(rec))
        except RuntimeError:
            pass  # no running loop (e.g. tests) — file sink already has it


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
                    "demo_id": rec["demo_id"],
                    "scenario_id": rec["scenario_id"],
                    "job_id": rec["job_id"],
                    "user": rec["user"],
                    **({"duration_s": str(rec["duration_s"])} if "duration_s" in rec else {}),
                },
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{_AI_ENDPOINT}/v2/track", json=[envelope])
    except Exception as e:
        logger.debug("App Insights send failed (non-fatal): %s", e)


def aggregate_stats() -> dict:
    """Aggregate the JSONL log into dashboard-ready counts."""
    total_started = 0
    by_demo: Counter = Counter()
    by_scenario: Counter = Counter()
    by_outcome: Counter = Counter()
    by_day: dict[str, int] = defaultdict(int)
    users: set[str] = set()
    durations: list[float] = []

    try:
        if ANALYTICS_PATH.exists():
            with ANALYTICS_PATH.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ev = rec.get("event", "")
                    if ev == "deploy_started":
                        total_started += 1
                        by_demo[rec.get("demo_id", "?")] += 1
                        by_scenario[rec.get("scenario_id", "?")] += 1
                        by_day[rec.get("ts", "")[:10]] += 1
                        users.add(rec.get("user", "?"))
                    elif ev in ("deploy_completed", "deploy_failed", "deploy_cancelled"):
                        by_outcome[ev.removeprefix("deploy_")] += 1
                        if "duration_s" in rec:
                            durations.append(rec["duration_s"])
    except Exception as e:
        logger.warning("Analytics aggregation failed: %s", e)

    finished = sum(by_outcome.values())
    return {
        "total_deployments": total_started,
        "distinct_users": len(users),
        "by_demo": dict(by_demo.most_common()),
        "by_scenario": dict(by_scenario.most_common()),
        "outcomes": dict(by_outcome),
        "success_rate": round(by_outcome.get("completed", 0) / finished, 3) if finished else None,
        "median_duration_s": sorted(durations)[len(durations) // 2] if durations else None,
        "per_day": dict(sorted(by_day.items())),
    }
