"""In-memory job state store for deployment jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

MAX_JOBS_PER_USER = 200


@dataclass
class JobState:
    job_id: str
    demo_id: str
    workspace_name: str
    user_id: str
    status: str = "pending"  # pending | running | completed | failed
    steps: list[dict] = field(default_factory=list)
    error: str | None = None
    workspace_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _events: list[dict] = field(default_factory=list, repr=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

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

    def create_job(
        self, demo_id: str, workspace_name: str, user_id: str
    ) -> JobState:
        job_id = str(uuid4())
        job = JobState(
            job_id=job_id,
            demo_id=demo_id,
            workspace_name=workspace_name,
            user_id=user_id,
        )
        self._jobs[job_id] = job
        self._evict_old_jobs(user_id)
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
                except (json.JSONDecodeError, TypeError):
                    pass
            # Extract workspace_id from "workspace" step
            if step_name == "workspace" and data.get("itemId"):
                job.workspace_id = data["itemId"]
        elif event_type == "error" and isinstance(data, dict):
            job.error = data.get("message", "Deployment failed")
            if data.get("workspaceId"):
                job.workspace_id = data["workspaceId"]

        # Notify all subscribers (non-blocking)
        for queue in list(job._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping SSE event for slow subscriber on job %s", job_id)

    def set_status(self, job_id: str, status: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = status
            job.updated_at = datetime.now(timezone.utc)

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
            [j for j in user_jobs if j.status in ("completed", "failed")],
            key=lambda j: j.created_at,
        )
        while len(user_jobs) > MAX_JOBS_PER_USER and terminal:
            old = terminal.pop(0)
            del self._jobs[old.job_id]
            user_jobs = [j for j in self._jobs.values() if j.user_id == user_id]


# Singleton
job_store = JobStore()
