"""Azure ARM proxy endpoints — subscriptions and resource groups."""

import re
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth import get_management_token
from app.azure_client import AzureClient

router = APIRouter(prefix="/api/azure", tags=["azure"])
limiter = Limiter(key_func=get_remote_address)

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@router.get("/subscriptions")
@limiter.limit("30/minute")
async def list_subscriptions(
    request: Request,
    token: str = Depends(get_management_token),
):
    """List Azure subscriptions accessible to the signed-in user."""
    client = AzureClient(token)
    try:
        return await client.list_subscriptions()
    finally:
        await client.close()


@router.get("/resource-groups")
@limiter.limit("30/minute")
async def list_resource_groups(
    subscriptionId: str,
    request: Request,
    token: str = Depends(get_management_token),
):
    """List resource groups in a subscription."""
    if not _UUID.match(subscriptionId):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid subscriptionId")
    client = AzureClient(token)
    try:
        return await client.list_resource_groups(subscriptionId)
    finally:
        await client.close()


@router.get("/locations")
@limiter.limit("30/minute")
async def list_locations(
    subscriptionId: str,
    request: Request,
    token: str = Depends(get_management_token),
):
    """List Azure regions available to a subscription (for the region picker)."""
    if not _UUID.match(subscriptionId):
        raise HTTPException(status_code=400, detail="Invalid subscriptionId")
    client = AzureClient(token)
    try:
        return await client.list_locations(subscriptionId)
    finally:
        await client.close()
