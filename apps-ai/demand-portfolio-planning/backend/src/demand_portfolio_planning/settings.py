from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEMO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_DEMO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_ai_project_endpoint: str = ""
    azure_foundry_model: str = "gpt-4.1-mini"
    azure_tenant_id: str | None = None
    azure_ai_subscription_id: str | None = None

    cors_allow_origins: list[str] = [
        "http://localhost:5248",
        "http://localhost:8138",
    ]


def get_settings() -> Settings:
    return Settings()
