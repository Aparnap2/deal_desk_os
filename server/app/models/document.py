from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    OUTDATED = "outdated"


class DealDocument(TimestampMixin, Base):
    __tablename__ = "deal_documents"

    id: Mapped[Identifier]
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(SAEnum(DocumentStatus), default=DocumentStatus.DRAFT, nullable=False)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    deal: Mapped["Deal"] = relationship(back_populates="documents")
