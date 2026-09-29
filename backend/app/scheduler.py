import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_MINUTES = 5


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        lambda: logger.info("scheduler heartbeat"),
        "interval",
        minutes=HEARTBEAT_INTERVAL_MINUTES,
        id="heartbeat",
    )
    logger.info("scheduler started")
    scheduler.start()


if __name__ == "__main__":
    main()
