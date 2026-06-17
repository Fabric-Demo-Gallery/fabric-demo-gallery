"""Live Eventstream replay endpoints.

Lets the UI push a demo's sample CSV through a Fabric Eventstream custom endpoint
so the Real-Time Dashboard and Activator react live. The user supplies the custom
endpoint connection string (copied from the Fabric portal).
"""

import json
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.deployer import DEMOS_DIR
from app.job_runner import _find_rti_csv
from app import stream_runner

router = APIRouter(prefix="/api/stream", tags=["stream"])
limiter = Limiter(key_func=get_remote_address)

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class StartStreamRequest(BaseModel):
    demo_id: str = Field(..., alias="demoId")
    scenario_id: str = Field("real-time-intelligence", alias="scenarioId")
    connection_string: str = Field(..., alias="connectionString")
    interval: float = Field(1.0)
    batch_size: int = Field(5, alias="batchSize")

    model_config = {"populate_by_name": True}


class StopStreamRequest(BaseModel):
    session_id: str = Field(..., alias="sessionId")

    model_config = {"populate_by_name": True}


def _resolve_kql_config(demo_id: str, scenario_id: str) -> dict:
    """Read the per-demo kqlConfig (tableName, timestampColumn) for the scenario."""
    custom_path = DEMOS_DIR / demo_id / "manifest.custom.json"
    if not custom_path.exists():
        return {}
    try:
        data = json.loads(custom_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    for entry in data.get("scenarios", []):
        if entry.get("id") == scenario_id:
            return entry.get("kqlConfig", {})
    return {}


@router.post("/start")
@limiter.limit("30/hour")
async def start_stream(body: StartStreamRequest, request: Request):
    if not _SAFE_ID.match(body.demo_id) or not _SAFE_ID.match(body.scenario_id):
        raise HTTPException(status_code=400, detail="Invalid demo_id or scenario_id")
    conn = (body.connection_string or "").strip()
    if "Endpoint=sb://" not in conn or "EntityPath=" not in conn:
        raise HTTPException(
            status_code=400,
            detail="Connection string must be an Event Hub custom-endpoint string including EntityPath.",
        )

    kql = _resolve_kql_config(body.demo_id, body.scenario_id)
    table_name = kql.get("tableName", "")
    timestamp_col = kql.get("timestampColumn", "")
    csv_filename = _find_rti_csv(body.demo_id, table_name)
    if not csv_filename:
        raise HTTPException(status_code=404, detail="No sample CSV found for this demo")

    try:
        session = await stream_runner.start_stream(
            conn_str=conn,
            demo_id=body.demo_id,
            csv_filename=csv_filename,
            table_name=table_name,
            timestamp_col=timestamp_col,
            interval=body.interval,
            batch_size=body.batch_size,
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    return session.to_dict()


@router.post("/stop")
async def stop_stream(body: StopStreamRequest):
    if not stream_runner.stop_stream(body.session_id):
        raise HTTPException(status_code=404, detail="Stream session not found")
    return {"stopped": True, "sessionId": body.session_id}


@router.get("/status/{session_id}")
async def stream_status(session_id: str):
    session = stream_runner.get_status(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Stream session not found")
    return session.to_dict()
