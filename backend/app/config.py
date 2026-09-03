from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemma-3-27b-it"]


class Settings(BaseSettings):
    """Runtime configuration, read from the environment.

    Locally the values come from backend/.env; on Vercel and in GitHub Actions
    from the environment. Nothing here has a secret as default.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Empty by default so the app still boots (and /api/health can explain why)
    # when the database is not configured yet.
    database_url: str = ""
    environment: str = "development"

    # Gemini, for the scraper only: the API on Vercel never calls the model and
    # never sees the key. Empty key → evaluation skipped, and the run says so.
    gemini_api_key: str = ""

    # The cascade, in order. NoDecode is load-bearing: without it
    # pydantic-settings tries to read the env var as JSON before any validator
    # runs, and a comma-separated list blows up at parse time.
    gemini_models: Annotated[list[str], NoDecode] = DEFAULT_GEMINI_MODELS

    @field_validator("gemini_models", mode="before")
    @classmethod
    def split_models(cls, value: object) -> object:
        """Accept a comma-separated string, since that is all an env var can carry."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
