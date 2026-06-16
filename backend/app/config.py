from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    azure_client_id: str = ""  # Required in production; optional for local dev (az CLI auth)
    azure_tenant_id: str = ""  # Required in production; optional for local dev
    azure_client_secret: str = ""  # Not used for SPA flow, kept for future OBO
    frontend_url: str = "http://localhost:3000"
    fabric_api_base: str = "https://api.fabric.microsoft.com/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
