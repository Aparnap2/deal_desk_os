from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.event import EventOutbox, EventStatus

logger = get_logger(__name__)


async def enqueue_event(
    session: AsyncSession,
    *,
    deal_id: str | None,
    event_type: str,
    payload: dict,
    channel: str = "n8n",
    schedule_in_seconds: int = 0,
) -> EventOutbox:
    event = EventOutbox(
        deal_id=deal_id,
        event_type=event_type,
        payload=payload,
        channel=channel,
        next_run_at=datetime.now(timezone.utc) + timedelta(seconds=schedule_in_seconds),
    )
    session.add(event)
    await session.flush()
    logger.info("event.outbox.enqueued", event_type=event_type, channel=channel)
    return event


async def dispatch_pending_events(
    session: AsyncSession,
    handler: Callable[[EventOutbox], Awaitable[None]] | None = None,
) -> int:
    result = await session.execute(
        select(EventOutbox).where(EventOutbox.status == EventStatus.PENDING)  # type: ignore[arg-type]
    )
    events = result.scalars().all()
    dispatched = 0
    for event in events:
        try:
            if handler is not None:
                await handler(event)
            event.status = EventStatus.DISPATCHED
            event.attempts += 1
            event.last_error = None
            dispatched += 1
            logger.info("event.outbox.dispatched", event_type=event.event_type, channel=event.channel)
        except Exception as exc:  # pragma: no cover - defensive fallback
            event.status = EventStatus.FAILED
            event.attempts += 1
            event.last_error = str(exc)
            event.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=30 * event.attempts)
            logger.warning("event.outbox.failed", event_id=event.id, error=str(exc))
    return dispatched
