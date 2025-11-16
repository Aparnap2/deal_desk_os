from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class DealStage(str, Enum):
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    SOLUTIONING = "solutioning"
    PRICING = "pricing"
    LEGAL_REVIEW = "legal_review"
    FINANCE_REVIEW = "finance_review"
    EXEC_APPROVAL = "executive_approval"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class DealRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GuardrailStatus(str, Enum):
    PASS = "pass"
    VIOLATED = "violated"


class OrchestrationMode(str, Enum):
    MANUAL = "manual"
    ORCHESTRATED = "orchestrated"


class Deal(TimestampMixin, Base):
    __tablename__ = "deals"

    id: Mapped[Identifier]
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    stage: Mapped[DealStage] = mapped_column(SAEnum(DealStage), default=DealStage.PROSPECTING, nullable=False)
    risk: Mapped[DealRisk] = mapped_column(SAEnum(DealRisk), default=DealRisk.MEDIUM, nullable=False)
    probability: Mapped[int] = mapped_column(default=25, nullable=False)
    expected_close: Mapped[date | None] = mapped_column(Date, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=2), default=0, nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    quote_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    agreement_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    guardrail_status: Mapped[GuardrailStatus] = mapped_column(
        SAEnum(GuardrailStatus), default=GuardrailStatus.PASS, nullable=False
    )
    guardrail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    orchestration_mode: Mapped[OrchestrationMode] = mapped_column(
        SAEnum(OrchestrationMode), default=OrchestrationMode.ORCHESTRATED, nullable=False
    )
    operational_cost: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    manual_cost_baseline: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    esign_envelope_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guardrail_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Invoice tracking
    invoice_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invoiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User | None"] = relationship(back_populates="owned_deals")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
    documents: Mapped[list["DealDocument"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
    events: Mapped[list["EventOutbox"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
    staged_invoices: Mapped[list["InvoiceStaging"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="deal", cascade="all,delete-orphan")
