"""Authentication utilities for Azure AD token validation and Fabric API access."""

import base64
import json
import os
import re
import subprocess
import logging

import jwt as pyjwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_is_production = os.getenv("WEBSITE_SITE_NAME") is not None

# ── Entra JWT signature verification ─────────────────────────────────────────
# The backend never makes authorization decisions beyond keying the per-user
# job store (list/cancel/delete of job METADATA) — the Fabric API is the real
# authz boundary for everything else. But an unverified decode would let a
# forged token enumerate or cancel another user's job metadata, so tokens are
# verified against Microsoft's published signing keys before any claim is
# trusted. v1.0 and v2.0 Entra tokens share the same signing keys; the common
# discovery endpoint serves both. PyJWKClient caches resolved keys (LRU), so
# the blocking JWKS fetch happens only on process start and key rotation.
_JWKS_URL = "https://login.microsoftonline.com/common/discovery/keys"
_jwks_client = PyJWKClient(_JWKS_URL, cache_keys=True, timeout=10)

# Delegated Fabric-API tokens carry one of these audiences depending on the
# token version / acquisition path (URI forms for v1-style resources, GUID =
# the Power BI Service first-party app that fronts the Fabric API). Trailing-
# slash variants included: Entra emits both forms depending on how the
# resource was requested.
_ACCEPTED_AUDIENCES = [
    "https://api.fabric.microsoft.com",
    "https://api.fabric.microsoft.com/",
    "https://analysis.windows.net/powerbi/api",
    "https://analysis.windows.net/powerbi/api/",
    "00000009-0000-0000-c000-000000000000",
]

# Multi-tenant app: the tenant id in the issuer varies per user, so validate
# the issuer SHAPE (Microsoft login hosts only) rather than an exact string.
_ISSUER_RE = re.compile(
    r"^https://(sts\.windows\.net|login\.microsoftonline\.com)/[0-9a-fA-F-]{36}(/v2\.0)?/?$"
)


def _verify_token(token: str) -> dict:
    """Verify an Entra JWT (signature, expiry, audience, issuer shape) and
    return its claims. Raises jwt.PyJWTError / PyJWKClientError on failure."""
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    claims = pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=_ACCEPTED_AUDIENCES,
        leeway=60,
        options={"require": ["exp", "iss", "aud"]},
    )
    if not _ISSUER_RE.match(str(claims.get("iss", ""))):
        raise pyjwt.InvalidIssuerError("Issuer is not a Microsoft Entra login host")
    return claims


def _unverified_claims(token: str) -> dict:
    """Best-effort claim extraction WITHOUT verification — dev fallback only."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


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
        "https://kusto.fabric.microsoft.com",
    }
    if resource not in _ALLOWED_RESOURCES:
        raise HTTPException(status_code=400, detail="Invalid resource")
    # The Kusto data plane requires the scope form (az has no static resource
    # alias for it); other resources work with --resource.
    if resource == "https://kusto.fabric.microsoft.com":
        args = ["az", "account", "get-access-token", "--scope",
                f"{resource}/.default", "--query", "accessToken", "-o", "tsv"]
    else:
        args = ["az", "account", "get-access-token", "--resource", resource,
                "--query", "accessToken", "-o", "tsv"]
    result = subprocess.run(
        args, capture_output=True, text=True, shell=False,
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


async def get_kusto_token(request: Request) -> str:
    """Get a token for Eventhouse/KQL data-plane (Kusto) REST calls.

    The Eventhouse query endpoint (``*.kusto.fabric.microsoft.com``) requires a
    token whose audience is ``https://kusto.fabric.microsoft.com`` — the
    api.fabric.microsoft.com token is rejected with 401. The frontend acquires
    this with the ``https://kusto.fabric.microsoft.com/.default`` scope; in dev we
    fall back to the az CLI (requires ``az login --scope
    https://kusto.fabric.microsoft.com/.default`` once).
    """
    tok = request.headers.get("x-kusto-token", "")
    if tok:
        return tok
    return _get_az_cli_token("https://kusto.fabric.microsoft.com")

def get_user_id(token: str) -> str:
    """Extract the user id (oid or sub claim) from a VERIFIED JWT.

    The id keys the per-user job store, so in production a token that fails
    signature/audience/issuer verification is rejected outright (401) instead
    of degrading to a shared identity. In local dev (az CLI tokens, no
    WEBSITE_SITE_NAME) verification is still attempted, but failure degrades
    to an unverified parse so offline development keeps working.
    """
    try:
        claims = _verify_token(token)
        return claims.get("oid") or claims.get("sub") or "dev-user"
    except Exception as e:
        if _is_production:
            logger.warning("Token verification failed: %s", str(e)[:200])
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired sign-in token. Please sign out and sign in again.",
            )
        try:
            claims = _unverified_claims(token)
            return claims.get("oid") or claims.get("sub") or "dev-user"
        except Exception:
            return "dev-user"


def get_user_email(token: str) -> str | None:
    """Extract the user's sign-in name (UPN/email) from a JWT token.

    Used only for usage analytics — never exposed through public endpoints,
    and never used for authorization. Callers always invoke get_user_id first
    (which enforces verification in production), so a cheap unverified parse
    is safe here and keeps analytics from ever failing a request.
    Returns None for az CLI tokens or on parse failure.
    """
    try:
        claims = _unverified_claims(token)
        return claims.get("preferred_username") or claims.get("upn") or claims.get("unique_name") or claims.get("email")
    except Exception:
        return None
