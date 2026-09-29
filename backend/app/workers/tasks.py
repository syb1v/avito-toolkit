import logging

import dramatiq

logger = logging.getLogger(__name__)


@dramatiq.actor(queue_name="crawl", max_retries=3)
def crawl_search(search_id: str) -> None:
    """Обход поиска и запись снапшотов. Реализация — фаза 1."""
    logger.info("crawl_search received", extra={"search_id": search_id})
    raise dramatiq.errors.Retry("обход поиска будет реализован в фазе 1")


@dramatiq.actor(queue_name="analytics")
def recalc_daily_analytics(search_id: str) -> None:
    """Пересчёт дневных агрегатов. Реализация — фаза 2."""
    logger.info("recalc_daily_analytics received", extra={"search_id": search_id})
