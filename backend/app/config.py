from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_version: str = "0.1.0"
    environment: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://avito:avito@localhost:5432/avito"
    redis_url: str = "redis://localhost:6379/0"

    llm_model: str = "deepseek/deepseek-chat"
    deepseek_api_key: str | None = None
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024

    proxy_enabled: bool = False
    proxy_url: str | None = None

    crawl_rate_per_minute: int = 12
    crawl_max_pages_per_run: int = 20
    crawl_delay_min_seconds: float = 5.0
    crawl_delay_max_seconds: float = 15.0

    avito_client_id: str | None = None
    avito_client_secret: str | None = None
    avito_user_id: int | None = None

    reprice_hitl_threshold_pct: float = 10.0
    reprice_max_step_pct: float = 5.0

    @field_validator("avito_user_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
