from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class AuditCategory(str, Enum):
    GUARDRAIL = "guardrail"
    PAYMENT = "payment"
    STATE_TRANSITION = "state_transition"
    SYSTEM = "system"
    INVOICE = "invoice"
    ACCOUNTING = "accounting"


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[Identifier]
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=True, index=True)
    staged_invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoice_staging.id", ondelete="CASCADE"), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(80), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[AuditCategory] = mapped_column(SAEnum(AuditCategory), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    deal: Mapped["Deal | None"] = relationship(back_populates="audit_logs")
    invoice: Mapped["Invoice | None"] = relationship(back_populates="audit_logs")
    staged_invoice: Mapped["InvoiceStaging | None"] = relationship(back_populates="audit_logs")
