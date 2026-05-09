from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    azure_client_id: str
    azure_tenant_id: str
    azure_client_secret: str
    frontend_url: str = "http://localhost:3000"
    fabric_api_base: str = "https://api.fabric.microsoft.com/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
