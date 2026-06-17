"""Live Eventstream replay.

Pushes rows from a demo's sample CSV to a Fabric Eventstream **custom endpoint**
(an Event Hubs-compatible connection string the user copies from the Fabric
portal). This simulates a live data feed so the Real-Time Dashboard and Activator
react in real time during a demo.

The connection string is a secret: it is held in memory for the lifetime of the
session only and is never logged or persisted.
"""

from __future__ import annotations

import asyncio
import csv as _csv
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.deployer import DEMOS_DIR

logger = logging.getLogger("app")

# Safety caps
_MAX_SESSIONS = 10
_MAX_ROWS = 50_000
_MIN_INTERVAL = 0.2
_MAX_INTERVAL = 10.0
_MAX_BATCH = 50


def _coerce(value: str):
    """Best-effort convert a CSV string cell to int/float, else keep as string."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


class StreamSession:
    """Tracks a single live-replay task."""

    def __init__(self, demo_id: str, table_name: str, interval: float, batch_size: int):
        self.id = uuid.uuid4().hex
        self.demo_id = demo_id
        self.table_name = table_name
        self.interval = interval
        self.batch_size = batch_size
        self.sent = 0
        self.running = True
        self.error = ""
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.task: asyncio.Task | None = None

    def to_dict(self) -> dict:
        return {
            "sessionId": self.id,
            "demoId": self.demo_id,
            "tableName": self.table_name,
            "sent": self.sent,
            "running": self.running,
            "error": self.error,
            "startedAt": self.started_at,
        }


_SESSIONS: dict[str, StreamSession] = {}


def _load_rows(demo_id: str, csv_filename: str) -> tuple[list[dict], list[str]]:
    """Load CSV rows (capped) from the demo's data folder. Guards path traversal."""
    data_dir = (DEMOS_DIR / demo_id / "data").resolve()
    csv_path = (data_dir / csv_filename).resolve()
    # Ensure the resolved path stays within the demo's data directory
    if data_dir not in csv_path.parents and csv_path != data_dir:
        raise ValueError("Invalid CSV path")
    if not csv_path.exists():
        raise FileNotFoundError(f"Sample file '{csv_filename}' not found")
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = _csv.DictReader(f)
        headers = reader.fieldnames or []
        for i, row in enumerate(reader):
            if i >= _MAX_ROWS:
                break
            rows.append(row)
    return rows, list(headers)


async def _run(session: StreamSession, conn_str: str, rows: list[dict], timestamp_col: str):
    """Background task: stream rows to the custom endpoint, looping forever."""
    try:
        # Imported lazily so the dependency is only required when streaming is used.
        from azure.eventhub.aio import EventHubProducerClient
        from azure.eventhub import EventData
    except ImportError:
        session.error = "azure-eventhub package not installed on the server."
        session.running = False
        return

    try:
        producer = EventHubProducerClient.from_connection_string(conn_str)
    except Exception as e:  # noqa: BLE001 - surface connection-string errors to the UI
        session.error = f"Invalid connection string: {str(e)[:160]}"
        session.running = False
        return

    idx = 0
    n = len(rows)
    try:
        async with producer:
            while session.running:
                batch = await producer.create_batch()
                for _ in range(session.batch_size):
                    raw = rows[idx % n]
                    idx += 1
                    event = {k: _coerce(v) for k, v in raw.items()}
                    if timestamp_col and timestamp_col in event:
                        event[timestamp_col] = datetime.now(timezone.utc).isoformat()
                    try:
                        batch.add(EventData(json.dumps(event)))
                    except ValueError:
                        # Batch full — send what we have and start a new one
                        break
                if len(batch) > 0:
                    await producer.send_batch(batch)
                    session.sent += len(batch)
                await asyncio.sleep(session.interval)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        session.error = str(e)[:200]
        logger.warning("Live stream session %s failed: %s", session.id, session.error)
    finally:
        session.running = False


async def start_stream(
    conn_str: str,
    demo_id: str,
    csv_filename: str,
    table_name: str,
    timestamp_col: str = "",
    interval: float = 1.0,
    batch_size: int = 5,
) -> StreamSession:
    """Start a live replay session and return it. Raises on bad input."""
    # Drop finished sessions to keep the map small
    for sid in [s for s, sess in _SESSIONS.items() if not sess.running]:
        _SESSIONS.pop(sid, None)
    if len([s for s in _SESSIONS.values() if s.running]) >= _MAX_SESSIONS:
        raise RuntimeError("Too many active streams. Stop one before starting another.")

    interval = max(_MIN_INTERVAL, min(_MAX_INTERVAL, float(interval)))
    batch_size = max(1, min(_MAX_BATCH, int(batch_size)))

    rows, _ = _load_rows(demo_id, csv_filename)
    if not rows:
        raise ValueError("Sample CSV has no rows to stream")

    session = StreamSession(demo_id, table_name, interval, batch_size)
    session.task = asyncio.create_task(_run(session, conn_str, rows, timestamp_col))
    _SESSIONS[session.id] = session
    return session


def stop_stream(session_id: str) -> bool:
    """Stop a running session. Returns True if a session was found."""
    session = _SESSIONS.get(session_id)
    if not session:
        return False
    session.running = False
    if session.task:
        session.task.cancel()
    return True


def get_status(session_id: str) -> StreamSession | None:
    return _SESSIONS.get(session_id)
