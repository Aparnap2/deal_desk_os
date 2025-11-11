from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.models.payment import PaymentStatus
from app.schemas.common import ORMModel, Timestamped


class PaymentBase(ORMModel):
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class PaymentCreate(PaymentBase):
    idempotency_key: str = Field(min_length=8, max_length=64)
    provider_reference: str | None = Field(default=None, max_length=120)
    simulate_failure: bool = False
    simulate_rollback: bool = False


class PaymentRead(Timestamped):
    id: str
    deal_id: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    idempotency_key: str
    provider_reference: str | None
    attempt_number: int
    failure_reason: str | None
    error_code: str | None
    completed_at: datetime | None
    rolled_back_at: datetime | None
    auto_recovered: bool
