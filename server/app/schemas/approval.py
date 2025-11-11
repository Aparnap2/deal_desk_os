from datetime import datetime

from pydantic import Field

from app.models.approval import ApprovalStatus
from app.schemas.common import ORMModel, Timestamped


class ApprovalBase(ORMModel):
    approver_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    notes: str | None = Field(default=None, max_length=1000)
    due_at: datetime | None = None
    sequence_order: int = Field(default=1, ge=1)


class ApprovalCreate(ApprovalBase):
    pass


class ApprovalUpdate(ORMModel):
    status: ApprovalStatus | None = None
    notes: str | None = Field(default=None, max_length=1000)
    due_at: datetime | None = None
    sequence_order: int | None = Field(default=None, ge=1)


class ApprovalRead(ApprovalBase, Timestamped):
    id: str
    deal_id: str
    completed_at: datetime | None = None
