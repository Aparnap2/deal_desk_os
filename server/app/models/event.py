from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class EventStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"


class EventOutbox(TimestampMixin, Base):
    __tablename__ = "event_outbox"

    id: Mapped[Identifier]
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[EventStatus] = mapped_column(SAEnum(EventStatus), default=EventStatus.PENDING, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(40), default="n8n", nullable=False)

    deal: Mapped["Deal | None"] = relationship(back_populates="events")
