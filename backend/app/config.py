from pathlib import Path
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables."""

    # Security & Rate Limiting
    APP_API_KEY: str = "assistball-secret-api-key"
    ASSISTBALL_API_KEY: Optional[str] = None
    ALLOWED_ORIGINS: Union[str, List[str]] = ["*"]
    RATE_LIMIT_PER_MIN: int = 20

    # Provider & Model Settings
    PROVIDER: str = "mock"
    MODEL_NAME: Optional[str] = None

    # Provider API Keys
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            origins = [origin.strip() for origin in v.split(",") if origin.strip()]
            return origins if origins else ["*"]
        return v


settings = Settings()
