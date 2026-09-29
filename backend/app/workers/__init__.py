import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.config import get_settings


def configure_broker() -> RedisBroker:
    broker = RedisBroker(url=get_settings().redis_url)
    dramatiq.set_broker(broker)
    return broker


broker = configure_broker()
