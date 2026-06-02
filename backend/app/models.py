"""Shared Pydantic models and validation constants."""

import re
from pydantic import BaseModel, field_validator

SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
SAFE_NAME = re.compile(r"^[a-zA-Z0-9 &_\-().]{1,100}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Feature → Fabric item types mapping
# Core items (Lakehouse, Notebook, DataPipeline) are always deployed.
FEATURE_ITEM_TYPES: dict[str, list[str]] = {
    "rti": ["Eventhouse", "KQLDatabase", "KQLDashboard"],
    "powerbi": ["SemanticModel", "Report"],
    "ml": [],          # future
    "fabric_iq": [],   # future
    "data_agents": [], # future
    "shortcuts": [],   # future
}

ALL_FEATURES = list(FEATURE_ITEM_TYPES.keys())


class DeployRequest(BaseModel):
    demo_id: str
    workspace_name: str | None = None
    workspace_id: str | None = None
    capacity_id: str | None = None
    features: list[str] | None = None  # None = all features enabled

    @field_validator("demo_id")
    @classmethod
    def validate_demo_id(cls, v: str) -> str:
        if not SAFE_ID.match(v):
            raise ValueError("Invalid demo_id")
        return v

    @field_validator("workspace_name")
    @classmethod
    def validate_workspace_name(cls, v: str | None) -> str | None:
        if v is not None and not SAFE_NAME.match(v):
            raise ValueError("Workspace name contains invalid characters")
        return v

    @field_validator("workspace_id", "capacity_id")
    @classmethod
    def validate_uuids(cls, v: str | None) -> str | None:
        if v is not None and not UUID_RE.match(v):
            raise ValueError("Invalid UUID format")
        return v

    @field_validator("features")
    @classmethod
    def validate_features(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for f in v:
                if f not in ALL_FEATURES:
                    raise ValueError(f"Unknown feature: {f}")
        return v
