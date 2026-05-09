"""Authentication utilities for Azure AD token validation and Fabric API access."""

import subprocess
import logging
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _get_az_cli_token(resource: str) -> str:
    """Get a token from az CLI (dev mode)."""
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True
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
    # Check X-Storage-Token header first (sent by frontend with MSAL tokens)
    if request and request.headers.get("x-storage-token"):
        return request.headers["x-storage-token"]
    # Dev mode fallback: use az CLI
    return _get_az_cli_token("https://storage.azure.com")
