from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.models.audit import AuditCategory, AuditLog
from app.models.deal import Deal, DealStage, GuardrailStatus


ALLOWED_TRANSITIONS: dict[DealStage, tuple[DealStage, ...]] = {
    DealStage.PROSPECTING: (DealStage.QUALIFICATION,),
    DealStage.QUALIFICATION: (DealStage.SOLUTIONING, DealStage.PRICING),
    DealStage.SOLUTIONING: (DealStage.PRICING,),
    DealStage.PRICING: (DealStage.LEGAL_REVIEW, DealStage.FINANCE_REVIEW),
    DealStage.LEGAL_REVIEW: (DealStage.EXEC_APPROVAL, DealStage.FINANCE_REVIEW, DealStage.CLOSED_LOST),
    DealStage.FINANCE_REVIEW: (DealStage.EXEC_APPROVAL, DealStage.CLOSED_LOST),
    DealStage.EXEC_APPROVAL: (DealStage.CLOSED_WON, DealStage.CLOSED_LOST),
    DealStage.CLOSED_WON: (),
    DealStage.CLOSED_LOST: (),
}


@dataclass(slots=True)
class TransitionResult:
    succeeded: bool
    reason: str | None = None


def _can_transition(current: DealStage, target: DealStage) -> bool:
    allowed: Iterable[DealStage] | None = ALLOWED_TRANSITIONS.get(current)
    return allowed is not None and target in allowed


def advance_stage(deal: Deal, target: DealStage) -> TransitionResult:
    if deal.stage == target:
        return TransitionResult(succeeded=True)

    if not _can_transition(deal.stage, target):
        return TransitionResult(False, f"stage transition {deal.stage} → {target} not permitted")

    if deal.guardrail_status is GuardrailStatus.VIOLATED and target == DealStage.CLOSED_WON:
        return TransitionResult(False, "cannot close won while guardrails are violated")

    now = datetime.now(timezone.utc)
    if target == DealStage.PRICING and deal.quote_generated_at is None:
        deal.quote_generated_at = now
    if target == DealStage.EXEC_APPROVAL and deal.agreement_signed_at is None:
        deal.agreement_signed_at = now
    if target == DealStage.CLOSED_WON and deal.payment_collected_at is None:
        deal.payment_collected_at = now

    deal.stage = target
    return TransitionResult(succeeded=True)


def record_transition_audit(deal: Deal, *, actor: str, session) -> None:
    entry = AuditLog(
        deal_id=deal.id,
        actor=actor,
        action="deal.stage.transition",
        category=AuditCategory.STATE_TRANSITION,
        details={"stage": deal.stage.value},
        critical=False,
    )
    session.add(entry)
