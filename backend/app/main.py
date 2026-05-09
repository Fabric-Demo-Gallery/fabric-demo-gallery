"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import demos, deploy, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Fabric Demo Gallery API",
    version="0.1.0",
    description="Backend for deploying industry-specific Microsoft Fabric demos",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demos.router)
app.include_router(workspaces.router)
app.include_router(deploy.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
