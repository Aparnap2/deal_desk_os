from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.approval import Approval, ApprovalStatus
from app.models.audit import AuditCategory, AuditLog
from app.models.deal import Deal, DealStage, GuardrailStatus
from app.schemas.approval import ApprovalCreate, ApprovalUpdate
from app.schemas.deal import DealCreate, DealUpdate
from app.services.guardrail_service import apply_guardrail_result, evaluate_pricing_guardrails
from app.services.outbox_service import enqueue_event


@dataclass(slots=True)
class DealFilters:
    search: str | None = None
    stage: DealStage | None = None
    owner_id: str | None = None
    min_probability: int | None = None
    max_probability: int | None = None


def _ensure_costs(deal: Deal) -> None:
    amount = Decimal(deal.amount)
    if not deal.operational_cost or deal.operational_cost == 0:
        deal.operational_cost = (amount * Decimal("0.005")).quantize(Decimal("0.01"))
    if not deal.manual_cost_baseline or deal.manual_cost_baseline == 0:
        deal.manual_cost_baseline = (amount * Decimal("0.02")).quantize(Decimal("0.01"))


async def list_deals(
    session: AsyncSession,
    *,
    filters: DealFilters,
    page: int,
    page_size: int,
) -> tuple[Sequence[Deal], int]:
    conditions = []
    if filters.search:
        like_term = f"%{filters.search.lower()}%"
        conditions.append(func.lower(Deal.name).like(like_term))
    if filters.stage:
        conditions.append(Deal.stage == filters.stage)
    if filters.owner_id:
        conditions.append(Deal.owner_id == filters.owner_id)
    if filters.min_probability is not None:
        conditions.append(Deal.probability >= filters.min_probability)
    if filters.max_probability is not None:
        conditions.append(Deal.probability <= filters.max_probability)

    base_query = select(Deal).options(
        selectinload(Deal.owner),
        selectinload(Deal.approvals),
    )
    if conditions:
        base_query = base_query.where(and_(*conditions))

    count_query = select(func.count()).select_from(Deal)
    if conditions:
        count_query = count_query.where(and_(*conditions))
    total = await session.scalar(count_query)
    result = await session.execute(
        base_query.order_by(Deal.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = result.scalars().unique().all()
    return items, int(total or 0)


async def get_deal(session: AsyncSession, deal_id: str) -> Deal | None:
    result = await session.execute(
        select(Deal)
        .where(Deal.id == deal_id)
        .options(
            joinedload(Deal.owner),
            selectinload(Deal.approvals),
            selectinload(Deal.documents),
        )
    )
    return result.scalars().first()


async def create_deal(session: AsyncSession, data: DealCreate) -> Deal:
    deal = Deal(
        name=data.name,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        stage=data.stage,
        risk=data.risk,
        probability=data.probability,
        expected_close=data.expected_close,
        industry=data.industry,
        owner_id=data.owner_id,
        discount_percent=data.discount_percent,
        payment_terms_days=data.payment_terms_days,
        quote_generated_at=data.quote_generated_at,
        agreement_signed_at=data.agreement_signed_at,
        payment_collected_at=data.payment_collected_at,
        orchestration_mode=data.orchestration_mode,
        operational_cost=data.operational_cost,
        manual_cost_baseline=data.manual_cost_baseline,
        esign_envelope_id=data.esign_envelope_id,
    )
    for index, approval_data in enumerate(data.approvals, start=1):
        deal.approvals.append(
            Approval(
                approver_id=approval_data.approver_id,
                status=approval_data.status,
                notes=approval_data.notes,
                due_at=approval_data.due_at,
                sequence_order=approval_data.sequence_order or index,
            )
        )

    if deal.stage in {
        DealStage.PRICING,
        DealStage.LEGAL_REVIEW,
        DealStage.FINANCE_REVIEW,
        DealStage.EXEC_APPROVAL,
        DealStage.CLOSED_WON,
    } and deal.quote_generated_at is None:
        deal.quote_generated_at = datetime.now(timezone.utc)

    _ensure_costs(deal)

    evaluation = evaluate_pricing_guardrails(
        amount=float(deal.amount),
        discount_percent=float(deal.discount_percent),
        payment_terms_days=deal.payment_terms_days,
        risk=deal.risk,
    )
    apply_guardrail_result(deal, evaluation)

    session.add(deal)
    session.add(
        AuditLog(
            deal_id=deal.id,
            actor="system",
            action="deal.created",
            category=AuditCategory.SYSTEM,
            details={"stage": deal.stage.value},
            critical=False,
        )
    )
    await session.flush()

    await enqueue_event(
        session,
        deal_id=deal.id,
        event_type="quote.generated",
        payload={"deal_id": deal.id, "stage": deal.stage.value},
    )

    if evaluation.status is GuardrailStatus.VIOLATED:
        session.add(
            AuditLog(
                deal_id=deal.id,
                actor="system",
                action="guardrail.violation",
                category=AuditCategory.GUARDRAIL,
                details={"reason": evaluation.reason},
                critical=True,
            )
        )
        await enqueue_event(
            session,
            deal_id=deal.id,
            event_type="guardrail.violation",
            payload={"reason": evaluation.reason},
        )
    elif evaluation.requires_manual_review:
        session.add(
            AuditLog(
                deal_id=deal.id,
                actor="system",
                action="guardrail.manual_review",
                category=AuditCategory.GUARDRAIL,
                details={"required_stage": evaluation.required_stage.value if evaluation.required_stage else None},
                critical=False,
            )
        )
        await enqueue_event(
            session,
            deal_id=deal.id,
            event_type="guardrail.review_required",
            payload={"required_stage": evaluation.required_stage.value if evaluation.required_stage else None},
        )

    await session.refresh(deal)
    return deal


async def update_deal(session: AsyncSession, deal: Deal, data: DealUpdate) -> Deal:
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(deal, field, value)
    _ensure_costs(deal)

    if {"amount", "discount_percent", "payment_terms_days", "risk"}.intersection(payload):
        evaluation = evaluate_pricing_guardrails(
            amount=float(deal.amount),
            discount_percent=float(deal.discount_percent),
            payment_terms_days=deal.payment_terms_days,
            risk=deal.risk,
        )
        apply_guardrail_result(deal, evaluation)
        if evaluation.status is GuardrailStatus.VIOLATED:
            session.add(
                AuditLog(
                    deal_id=deal.id,
                    actor="system",
                    action="guardrail.violation",
                    category=AuditCategory.GUARDRAIL,
                    details={"reason": evaluation.reason},
                    critical=True,
                )
            )
            await enqueue_event(
                session,
                deal_id=deal.id,
                event_type="guardrail.violation",
                payload={"reason": evaluation.reason},
            )
        elif evaluation.requires_manual_review:
            session.add(
                AuditLog(
                    deal_id=deal.id,
                    actor="system",
                    action="guardrail.manual_review",
                    category=AuditCategory.GUARDRAIL,
                    details={
                        "required_stage": evaluation.required_stage.value if evaluation.required_stage else None
                    },
                    critical=False,
                )
            )
            await enqueue_event(
                session,
                deal_id=deal.id,
                event_type="guardrail.review_required",
                payload={"required_stage": evaluation.required_stage.value if evaluation.required_stage else None},
            )
    await session.flush()
    await session.refresh(deal)
    return deal


async def upsert_approval(
    session: AsyncSession,
    approval: Approval,
    data: ApprovalUpdate,
) -> Approval:
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(approval, field, value)
    if payload.get("status") in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
        approval.completed_at = approval.completed_at or datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(approval)
    return approval


async def add_approval(session: AsyncSession, deal: Deal, data: ApprovalCreate) -> Approval:
    approval = Approval(
        approver_id=data.approver_id,
        status=data.status,
        notes=data.notes,
        due_at=data.due_at,
        sequence_order=data.sequence_order,
    )
    deal.approvals.append(approval)
    await session.flush()
    await session.refresh(approval)
    return approval
