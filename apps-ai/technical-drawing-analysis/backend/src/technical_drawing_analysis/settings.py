from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            DEMO_DIR / ".azure" / "technical-drawing-analysis" / ".env",
            DEMO_DIR / ".env",
        ),
        extra="ignore",
    )

    cors_allowed_origins: str = Field(default="*", alias="CORS_ALLOWED_ORIGINS")
    azure_tenant_id: str | None = Field(default=None, alias="AZURE_TENANT_ID")
    azure_ai_subscription_id: str | None = Field(default=None, alias="AZURE_AI_SUBSCRIPTION_ID")
    azure_ai_project_endpoint: str | None = Field(default=None, alias="AZURE_AI_PROJECT_ENDPOINT")
    azure_ai_services_endpoint: str | None = Field(default=None, alias="AZURE_AI_SERVICES_ENDPOINT")
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_foundry_model: str = Field(default="", alias="AZURE_FOUNDRY_MODEL")
    azure_token_scope: str = Field(default="https://ai.azure.com/.default", alias="AZURE_TOKEN_SCOPE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
