"""Job state store for deployment jobs — in-memory with JSON-file persistence.

Job history previously lived only in memory, so every backend restart (App
Service deploys, scale events) silently wiped the monitoring page — users
thought their deployments had vanished. Terminal jobs are now snapshotted to a
JSON file (App Service's /home persists across restarts) and reloaded on boot.
Running jobs are NOT restored — their asyncio task died with the old process —
they're marked failed on load so the UI tells the truth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

MAX_JOBS_PER_USER = 200

# App Service (Linux) persists /home across restarts; anywhere else fall back to
# a local data dir next to the app (dev) so behaviour is identical.
def _default_persist_path() -> Path:
    base = Path("/home/data") if Path("/home").is_dir() and os.access("/home", os.W_OK) else Path(__file__).resolve().parent.parent / "data"
    return base / "jobs.json"

PERSIST_PATH = Path(os.environ.get("JOB_STORE_PATH", str(_default_persist_path())))


@dataclass
class JobState:
    job_id: str
    demo_id: str
    workspace_name: str
    user_id: str
    user_email: str | None = None  # sign-in name, for usage analytics only
    status: str = "pending"  # pending | running | completed | failed | cancelled
    steps: list[dict] = field(default_factory=list)
    error: str | None = None
    workspace_id: str | None = None
    scenario_id: str | None = None
    azure_resources: dict | None = None  # e.g. {subscriptionId, resourceGroup, sqlServer}
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[dict] = field(default_factory=list, repr=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)
    _task: asyncio.Task | None = field(default=None, init=False, repr=False)

    def to_summary(self) -> dict:
        total = len(self.steps)
        completed = sum(1 for s in self.steps if s.get("status") == "completed")
        failed = sum(1 for s in self.steps if s.get("status") == "failed")
        running = sum(1 for s in self.steps if s.get("status") == "running")
        return {
            "job_id": self.job_id,
            "demo_id": self.demo_id,
            "workspace_name": self.workspace_name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "workspace_id": self.workspace_id,
            "scenario_id": self.scenario_id,
            "azure_resources": self.azure_resources,
            "error": self.error,
            "step_summary": {
                "total": total,
                "completed": completed,
                "failed": failed,
                "running": running,
            },
        }

    def to_detail(self) -> dict:
        return {
            **self.to_summary(),
            "steps": self.steps,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._load()

    # ── persistence ────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            if not PERSIST_PATH.exists():
                return
            raw = json.loads(PERSIST_PATH.read_text(encoding="utf-8"))
            for rec in raw:
                try:
                    status = rec["status"]
                    # A job that was mid-flight when the process died can never
                    # resume — surface that instead of a forever-"running" row.
                    if status in ("pending", "running"):
                        status = "failed"
                        rec["error"] = rec.get("error") or "Interrupted by a service restart."
                    job = JobState(
                        job_id=rec["job_id"],
                        demo_id=rec["demo_id"],
                        workspace_name=rec["workspace_name"],
                        user_id=rec["user_id"],
                        user_email=rec.get("user_email"),
                        status=status,
                        steps=rec.get("steps") or [],
                        error=rec.get("error"),
                        workspace_id=rec.get("workspace_id"),
                        scenario_id=rec.get("scenario_id"),
                        azure_resources=rec.get("azure_resources"),
                        created_at=datetime.fromisoformat(rec["created_at"]),
                        updated_at=datetime.fromisoformat(rec["updated_at"]),
                    )
                    self._jobs[job.job_id] = job
                except (KeyError, ValueError) as e:
                    logger.warning("Skipping corrupt persisted job record: %s", e)
            logger.info("Restored %d persisted jobs from %s", len(self._jobs), PERSIST_PATH)
        except Exception as e:
            # Persistence is best-effort — never block startup on a bad file.
            logger.warning("Could not load persisted jobs (%s); starting empty", e)

    def _save(self) -> None:
        try:
            PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            records = []
            for j in self._jobs.values():
                records.append({
                    "job_id": j.job_id,
                    "demo_id": j.demo_id,
                    "workspace_name": j.workspace_name,
                    "user_id": j.user_id,
                    "user_email": j.user_email,
                    "status": j.status,
                    "steps": j.steps,
                    "error": j.error,
                    "workspace_id": j.workspace_id,
                    "scenario_id": j.scenario_id,
                    "azure_resources": j.azure_resources,
                    "created_at": j.created_at.isoformat(),
                    "updated_at": j.updated_at.isoformat(),
                })
            # Atomic replace so a crash mid-write can't corrupt the file.
            fd, tmp = tempfile.mkstemp(dir=str(PERSIST_PATH.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f)
            os.replace(tmp, PERSIST_PATH)
        except Exception as e:
            logger.warning("Could not persist jobs: %s", e)

    def create_job(
        self, demo_id: str, workspace_name: str, user_id: str, scenario_id: str | None = None,
        user_email: str | None = None,
    ) -> JobState:
        job_id = str(uuid4())
        job = JobState(
            job_id=job_id,
            demo_id=demo_id,
            workspace_name=workspace_name,
            user_id=user_id,
            user_email=user_email,
            scenario_id=scenario_id,
        )
        self._jobs[job_id] = job
        self._evict_old_jobs(user_id)
        self._save()
        # Usage analytics — deferred import to avoid a circular dependency
        # (analytics reads PERSIST_PATH from this module).
        from app.analytics import record_deployment_event
        record_deployment_event(
            "deploy_started", demo_id=demo_id, scenario_id=scenario_id,
            job_id=job_id, user_id=user_id, email=user_email,
        )
        return job

    def get_job(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def list_jobs(self, user_id: str) -> list[dict]:
        jobs = [
            j.to_summary()
            for j in self._jobs.values()
            if j.user_id == user_id
        ]
        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        return jobs

    def emit_event(self, job_id: str, event: dict[str, Any]) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return

        job.updated_at = datetime.now(timezone.utc)
        job._events.append(event)

        event_type = event.get("event")
        data = event.get("data")

        if event_type == "plan" and isinstance(data, list):
            job.steps = data
            job.status = "running"
        elif event_type == "step" and isinstance(data, dict):
            step_name = data.get("name")
            for i, s in enumerate(job.steps):
                if s.get("name") == step_name:
                    job.steps[i] = {**s, **data}
                    break
            # Extract workspace_id from "done" step
            if step_name == "done" and data.get("status") == "completed":
                try:
                    detail = json.loads(data.get("detail", "{}"))
                    if detail.get("workspaceId"):
                        job.workspace_id = detail["workspaceId"]
                    if detail.get("azure"):
                        job.azure_resources = detail["azure"]
                except (json.JSONDecodeError, TypeError):
                    pass
            # Extract workspace_id from "workspace" step
            if step_name == "workspace" and data.get("itemId"):
                job.workspace_id = data["itemId"]
        elif event_type == "error" and isinstance(data, dict):
            job.error = data.get("message", "Deployment failed")
            if data.get("workspaceId"):
                job.workspace_id = data["workspaceId"]
            if data.get("azure"):
                job.azure_resources = data["azure"]

        # Snapshot on the events that change what the monitoring page shows.
        # Terminal transitions come through set_status; the "done"/"workspace"
        # steps carry the workspace id — cheap enough to save on every step.
        if event_type in ("plan", "step", "error"):
            self._save()

        # Notify all subscribers (non-blocking)
        for queue in list(job._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping SSE event for slow subscriber on job %s", job_id)

    def set_task(self, job_id: str, task: asyncio.Task) -> None:
        job = self._jobs.get(job_id)
        if job:
            job._task = task

    def cancel_job(self, job_id: str) -> bool:
        """Cancel the running asyncio task for a job. Returns True if cancelled."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job._task and not job._task.done():
            job._task.cancel()
            return True
        return False

    def set_status(self, job_id: str, status: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            was_terminal = job.status in ("completed", "failed", "cancelled")
            job.status = status
            job.updated_at = datetime.now(timezone.utc)
            self._save()
            # Usage analytics on the FIRST transition into a terminal state.
            if status in ("completed", "failed", "cancelled") and not was_terminal:
                from app.analytics import record_deployment_event
                # Which step broke? First failed step in the plan (best effort).
                failed_step = next(
                    (s.get("name") for s in job.steps if s.get("status") == "failed"), None
                ) if status == "failed" else None
                record_deployment_event(
                    f"deploy_{status}", demo_id=job.demo_id, scenario_id=job.scenario_id,
                    job_id=job.job_id, user_id=job.user_id, email=job.user_email,
                    duration_s=(job.updated_at - job.created_at).total_seconds(),
                    error=job.error if status == "failed" else None,
                    failed_step=failed_step,
                )

    def clear_workspace(self, job_id: str) -> None:
        """Forget a job's workspace after it was deleted in Fabric."""
        job = self._jobs.get(job_id)
        if job:
            job.workspace_id = None
            job.updated_at = datetime.now(timezone.utc)
            self._save()

    def subscribe(self, job_id: str) -> asyncio.Queue | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        job._subscribers.append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        job = self._jobs.get(job_id)
        if job and queue in job._subscribers:
            job._subscribers.remove(queue)

    def get_events(self, job_id: str) -> list[dict]:
        job = self._jobs.get(job_id)
        return list(job._events) if job else []

    def _evict_old_jobs(self, user_id: str) -> None:
        user_jobs = [
            j for j in self._jobs.values() if j.user_id == user_id
        ]
        if len(user_jobs) <= MAX_JOBS_PER_USER:
            return
        # Sort by created_at, evict oldest completed/failed jobs
        terminal = sorted(
            [j for j in user_jobs if j.status in ("completed", "failed", "cancelled")],
            key=lambda j: j.created_at,
        )
        while len(user_jobs) > MAX_JOBS_PER_USER and terminal:
            old = terminal.pop(0)
            del self._jobs[old.job_id]
            user_jobs = [j for j in self._jobs.values() if j.user_id == user_id]


# Singleton
job_store = JobStore()
