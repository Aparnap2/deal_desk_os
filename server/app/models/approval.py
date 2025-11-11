from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"

    id: Mapped[Identifier]
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    approver_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sequence_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    deal: Mapped["Deal"] = relationship(back_populates="approvals")
    approver: Mapped["User | None"] = relationship(back_populates="approvals")
