from functools import lru_cache

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
    browser_no_sandbox: bool = False
    browser_headless: bool = True
    browser_channel: str | None = "chromium"
    browser_user_data_dir: str | None = None

    crawl_rate_per_minute: int = 12
    crawl_max_pages_per_run: int = 10
    crawl_delay_min_seconds: float = 8.0
    crawl_delay_max_seconds: float = 20.0
    # auto | browser | hybrid | http: auto = браузер, если установлен patchright
    crawl_transport: str = "auto"

    reprice_hitl_threshold_pct: float = 10.0
    reprice_max_step_pct: float = 5.0

    match_min_score: int = 75
    match_max_candidates: int = 300
    match_top_n: int = 10
    alert_price_above_market_pct: float = 10.0

    moderation_enabled: bool = True
    moderation_ai_enabled: bool = True
    moderation_low_price_ratio: float = 0.35
    moderation_ai_candidate_ratio: float = 0.6
    moderation_duplicate_min_cluster: int = 5
    moderation_ai_batch_size: int = 10
    moderation_max_ai_items: int = 40
    moderation_descriptions_enabled: bool = True
    moderation_description_max_items: int = 10
    moderation_description_delay_min_seconds: float = 3.0
    moderation_description_delay_max_seconds: float = 6.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
