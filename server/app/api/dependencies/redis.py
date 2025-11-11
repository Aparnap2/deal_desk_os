from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def get_redis_client() -> AsyncIterator[Redis | None]:
    settings = get_settings()
    client: Redis | None = None
    try:
        client = Redis.from_url(settings.redis_url)
        yield client
    except Exception as exc:  # pragma: no cover - redis optional in tests
        logger.warning("redis.unavailable", error=str(exc))
        yield None
    finally:
        if client is not None:
            await client.close()
