"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.routers import azure, demos, deploy, jobs, stream, workspaces

# ── File logging ─────────────────────────────────────────────────────────────
_log_file = os.path.join(os.path.dirname(__file__), "..", "app.log")
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
for _log_name in ("app", "httpx"):
    _lg = logging.getLogger(_log_name)
    _lg.setLevel(logging.INFO)
    if not any(isinstance(h, logging.FileHandler) for h in _lg.handlers):
        _lg.addHandler(_file_handler)
# ─────────────────────────────────────────────────────────────────────────────


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


_is_production = os.getenv("WEBSITE_SITE_NAME") is not None  # Azure App Service sets this

app = FastAPI(
    title="Fabric Demo Gallery API",
    version="0.1.0",
    description="Backend for deploying industry-specific Microsoft Fabric demos",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})

settings = get_settings()

# CORS: restrict to known frontend origins (FRONTEND_URL may be comma-separated)
_allowed_origins = [o.strip() for o in settings.frontend_url.split(",") if o.strip()]
if not _is_production:
    _allowed_origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Storage-Token",
        "X-Management-Token",
        "X-OneLake-Token",
        "X-Search-Token",
        "X-Agent-Token",
        "X-Kusto-Token",
    ],
)

app.include_router(demos.router)
app.include_router(workspaces.router)
app.include_router(deploy.router)
app.include_router(azure.router)
app.include_router(jobs.router)
app.include_router(stream.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
