"""Authentication utilities for Azure AD token validation and Fabric API access."""

import os
import subprocess
import logging
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_is_production = os.getenv("WEBSITE_SITE_NAME") is not None


def _get_az_cli_token(resource: str) -> str:
    """Get a token from az CLI (dev mode only)."""
    if _is_production:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in.",
        )
    # Only allow known resource URLs to prevent injection
    _ALLOWED_RESOURCES = {
        "https://api.fabric.microsoft.com",
        "https://storage.azure.com",
        "https://management.azure.com",
    }
    if resource not in _ALLOWED_RESOURCES:
        raise HTTPException(status_code=400, detail="Invalid resource")
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise HTTPException(status_code=401, detail=f"az CLI token failed: {result.stderr[:200]}")
    return result.stdout.strip()


async def get_user_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Extract Bearer token or fall back to az CLI token (dev mode)."""
    if credentials and credentials.credentials:
        return credentials.credentials
    logger.info("No Bearer token — using az CLI token (dev mode)")
    return _get_az_cli_token("https://api.fabric.microsoft.com")


async def get_storage_token(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Get a storage.azure.com token for OneLake access."""
    if request and request.headers.get("x-storage-token"):
        return request.headers["x-storage-token"]
    return _get_az_cli_token("https://storage.azure.com")


async def get_management_token(request: Request) -> str:
    """Get an Azure management token for ARM API access."""
    tok = request.headers.get("x-management-token", "")
    if tok:
        return tok
    return _get_az_cli_token("https://management.azure.com")
