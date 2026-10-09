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
    proxy_list: str = ""
    proxy_rotation: str = "round_robin"
    proxy_cooldown_seconds: int = 300
    proxy_max_failures: int = 3
    proxy_healthcheck_enabled: bool = True
    proxy_healthcheck_url: str = "https://api.ipify.org?format=json"
    proxy_healthcheck_timeout: float = 10.0
    proxy_healthcheck_interval_minutes: int = 15
    proxy_antibot_cooldown_seconds: int = 1800
    browser_no_sandbox: bool = False
    browser_headless: bool = True
    browser_channel: str | None = "chromium"
    browser_user_data_dir: str | None = None
    # Картинки/шрифты нельзя резать: для антибот-фаервола Авито это признак бота
    browser_block_resources: bool = False

    crawl_rate_per_minute: int = 12
    # 0 = без лимита; по умолчанию ограничиваем, чтобы не уходить в бесконечность
    crawl_max_pages_per_run: int = 10
    # Сколько описаний догружать за обход (фильтры проверяют и заголовок, и описание)
    crawl_descriptions_per_run: int = 20
    crawl_delay_min_seconds: float = 8.0
    crawl_delay_max_seconds: float = 20.0
    # auto | browser | hybrid | http: auto = браузер, если установлен patchright
    crawl_transport: str = "auto"
    crawl_min_interval_minutes: int = 30
    crawl_challenge_cooldown_minutes: int = 60
    crawl_rate_limit_cooldown_minutes: int = 90
    crawl_breaker_failures: int = 3
    crawl_breaker_minutes: int = 120
    worker_pause_min_seconds: float = 2.0
    worker_pause_max_seconds: float = 7.0
    browser_humanize: bool = True
    # Проверка аккаунта — не чаще раза в N минут (защита от самоизбиения IP)
    account_check_cooldown_minutes: int = 10
    # Уход за аккаунтами: дневной лимит страниц и «отдых» после перегруза
    account_daily_page_limit: int = 80
    account_rest_minutes: int = 180
    # Прогрев: мягкие заходы для «живости» сессии
    account_warmup_enabled: bool = True
    account_warmup_idle_hours: int = 12
    account_warmup_interval_minutes: int = 60
    account_warmup_max_per_run: int = 3
    # Telegram-бот: токен от @BotFather, доступ по логину/паролю, сессия N дней
    telegram_bot_token: str | None = None
    telegram_login: str = "admin"
    telegram_password: str | None = None
    telegram_session_days: int = 30
    # Watchdog: воркер считается живым, если heartbeat не старше окна
    worker_alive_window_seconds: int = 120
    watchdog_interval_minutes: int = 5
    watchdog_queue_warn_depth: int = 25
    # Алерт «куки протухли»: если cookies не обновлялись дольше N часов.
    watchdog_cookies_max_age_hours: int = 72
    # Алерт «баланс AI API на исходе»: порог в валюте баланса (DeepSeek — CNY).
    watchdog_ai_balance_min: float = 1.0

    reprice_hitl_threshold_pct: float = 10.0
    reprice_max_step_pct: float = 5.0
    # Фаза 6: правки объявлений через кабинет продавца
    # dry_run — только фиксируем план (браузер не трогаем); live — реально меняем цену
    seller_edit_mode: str = "dry_run"
    # Авто-правки: ночной cron и главный выключатель из env (Redis-тумблер — второй гейт).
    reprice_auto_enabled: bool = False
    reprice_auto_cron: str = "0 0 * * *"
    reprice_summary_enabled: bool = True
    seller_edit_max_per_run: int = 5
    avito_edit_url_template: str = "https://www.avito.ru/items/edit/{item_id}"

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
    # AI-проверка контекста стоп-слов в описании (только спорные случаи).
    moderation_description_review_enabled: bool = True
    moderation_description_review_max_items: int = 20
    moderation_description_review_batch_size: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
