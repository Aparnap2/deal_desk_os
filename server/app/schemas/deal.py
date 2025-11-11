from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import Field

from app.models.deal import DealRisk, DealStage, GuardrailStatus, OrchestrationMode
from app.schemas.common import ORMModel, Timestamped
from app.schemas.user import UserRead


class DealBase(ORMModel):
    name: str = Field(min_length=3, max_length=255)
    description: str | None = None
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stage: DealStage = DealStage.PROSPECTING
    risk: DealRisk = DealRisk.MEDIUM
    probability: int = Field(default=25, ge=0, le=100)
    expected_close: Optional[date] = None
    industry: str | None = Field(default=None, max_length=120)
    owner_id: str | None = None
    discount_percent: Decimal = Field(default=0, ge=0, le=100)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    quote_generated_at: Optional[datetime] = None
    agreement_signed_at: Optional[datetime] = None
    payment_collected_at: Optional[datetime] = None
    orchestration_mode: OrchestrationMode = OrchestrationMode.ORCHESTRATED
    operational_cost: Decimal = Field(default=0, ge=0)
    manual_cost_baseline: Decimal = Field(default=0, ge=0)
    esign_envelope_id: str | None = Field(default=None, max_length=120)


class DealCreate(DealBase):
    approvals: List["ApprovalCreate"] = Field(default_factory=list)


class DealUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stage: DealStage | None = None
    risk: DealRisk | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close: Optional[date] = None
    industry: str | None = Field(default=None, max_length=120)
    owner_id: str | None = None
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    quote_generated_at: Optional[datetime] = None
    agreement_signed_at: Optional[datetime] = None
    payment_collected_at: Optional[datetime] = None
    orchestration_mode: OrchestrationMode | None = None
    operational_cost: Decimal | None = Field(default=None, ge=0)
    manual_cost_baseline: Decimal | None = Field(default=None, ge=0)
    esign_envelope_id: str | None = Field(default=None, max_length=120)


class DealSummary(ORMModel):
    id: str
    name: str
    amount: Decimal
    probability: int
    stage: DealStage
    risk: DealRisk
    owner: UserRead | None = None
    expected_close: Optional[date] = None
    updated_at: datetime
    discount_percent: Decimal
    payment_terms_days: int
    guardrail_status: GuardrailStatus
    orchestration_mode: OrchestrationMode
    quote_generated_at: Optional[datetime] = None
    payment_collected_at: Optional[datetime] = None


class DealRead(DealSummary, Timestamped):
    description: str | None
    currency: str
    industry: str | None
    approvals: List["ApprovalRead"] = Field(default_factory=list)
    documents: List["DealDocumentRead"] = Field(default_factory=list)
    guardrail_reason: str | None = None
    operational_cost: Decimal
    manual_cost_baseline: Decimal
    esign_envelope_id: str | None = None


class DealCollection(ORMModel):
    items: List[DealSummary]
    total: int
    page: int
    page_size: int


from app.schemas.approval import ApprovalCreate, ApprovalRead  # noqa: E402  circular
from app.schemas.document import DealDocumentRead  # noqa: E402
