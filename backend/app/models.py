"""Shared Pydantic models and validation constants."""

import re
from pydantic import BaseModel, field_validator

SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
SAFE_NAME = re.compile(r"^[a-zA-Z0-9 ,&_\-().]{1,100}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


_SAFE_RG = re.compile(r"^[a-zA-Z0-9._\-()]{1,90}$")
_SAFE_STORAGE_ACCT = re.compile(r"^[a-z0-9]{3,24}$")
_SAFE_LOCATION = re.compile(r"^[a-z0-9]{3,40}$")
_SAFE_SCENARIO = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class DeployRequest(BaseModel):
    demo_id: str
    workspace_name: str | None = None
    workspace_id: str | None = None
    capacity_id: str | None = None
    # Scenario / Azure fields
    scenario_id: str | None = None
    subscription_id: str | None = None
    resource_group: str | None = None
    storage_account_name: str | None = None
    azure_location: str | None = "eastus"
    create_resource_group: bool = False

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

    @field_validator("workspace_id", "capacity_id", "subscription_id")
    @classmethod
    def validate_uuids(cls, v: str | None) -> str | None:
        if v is not None and not UUID_RE.match(v):
            raise ValueError("Invalid UUID format")
        return v

    @field_validator("resource_group")
    @classmethod
    def validate_resource_group(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_RG.match(v):
            raise ValueError("Invalid resource group name")
        return v

    @field_validator("storage_account_name")
    @classmethod
    def validate_storage_account_name(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_STORAGE_ACCT.match(v):
            raise ValueError("Storage account name must be 3-24 lowercase alphanumeric characters")
        return v

    @field_validator("azure_location")
    @classmethod
    def validate_azure_location(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_LOCATION.match(v):
            raise ValueError("Invalid azure_location")
        return v

    @field_validator("scenario_id")
    @classmethod
    def validate_scenario_id(cls, v: str | None) -> str | None:
        if v is not None and not _SAFE_SCENARIO.match(v):
            raise ValueError("Invalid scenario_id")
        return v
