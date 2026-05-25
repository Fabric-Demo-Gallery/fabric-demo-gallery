"""Workspace listing endpoint."""

from fastapi import APIRouter, Depends

from app.auth import get_user_token
from app.fabric_client import FabricClient

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("")
async def get_workspaces(token: str = Depends(get_user_token)):
    """List the user's Fabric workspaces."""
    client = FabricClient(token)
    try:
        workspaces = await client.list_workspaces()
        return [
            {
                "id": ws["id"],
                "displayName": ws["displayName"],
                "capacityId": ws.get("capacityId"),
            }
            for ws in workspaces
        ]
    finally:
        await client.close()


@router.get("/capacities")
async def get_capacities(token: str = Depends(get_user_token)):
    """List the user's available Fabric capacities."""
    client = FabricClient(token)
    try:
        capacities = await client.list_capacities()
        return capacities
    finally:
        await client.close()
