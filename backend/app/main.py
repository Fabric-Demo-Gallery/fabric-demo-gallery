"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.routers import demos, deploy, workspaces


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

# CORS: restrict to known frontend origins
_allowed_origins = [settings.frontend_url]
if not _is_production:
    _allowed_origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Storage-Token"],
)

app.include_router(demos.router)
app.include_router(workspaces.router)
app.include_router(deploy.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
