from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditCategory, AuditLog
from app.models.deal import Deal, DealStage
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate
from app.services.outbox_service import enqueue_event
from app.services.state_machine import advance_stage, record_transition_audit

logger = get_logger(__name__)

LOCK_PREFIX = "dealdesk:payment:idemp:"
LOCK_TTL_SECONDS = 3600


async def _acquire_idempotency_lock(redis_client: Optional[Redis], key: str) -> bool:
    if redis_client is None:
        return True
    async with redis_client.pipeline(transaction=True) as pipe:  # type: ignore[attr-defined]
        pipe.setnx(key, 1)
        pipe.expire(key, LOCK_TTL_SECONDS)
        created, _ = await pipe.execute()
        return bool(created)


async def _mark_collection(deal: Deal, session: AsyncSession, *, actor: str) -> None:
    result = advance_stage(deal, DealStage.CLOSED_WON)
    if result.succeeded:
        await session.flush()
        record_transition_audit(deal, actor=actor, session=session)


async def process_payment(
    session: AsyncSession,
    *,
    deal: Deal,
    payload: PaymentCreate,
    redis_client: Optional[Redis] = None,
) -> Payment:
    key = f"{LOCK_PREFIX}{payload.idempotency_key}"
    if not await _acquire_idempotency_lock(redis_client, key):
        logger.info("payment.idempotency.skipped", deal_id=deal.id)
        existing = await session.execute(
            select(Payment).where(Payment.idempotency_key == payload.idempotency_key)
        )
        payment = existing.scalars().first()
        if payment is None:  # pragma: no cover - defensive
            raise RuntimeError("idempotency key locked but payment missing")
        return payment

    existing_result = await session.execute(
        select(Payment).where(Payment.idempotency_key == payload.idempotency_key)
    )
    payment = existing_result.scalars().first()
    now = datetime.now(timezone.utc)

    if payment is None:
        attempt_count_result = await session.execute(
            select(Payment.attempt_number).where(Payment.deal_id == deal.id).order_by(Payment.attempt_number.desc())
        )
        last_attempt = attempt_count_result.scalars().first() or 0
        payment = Payment(
            deal_id=deal.id,
            amount=payload.amount,
            currency=payload.currency,
            idempotency_key=payload.idempotency_key,
            provider_reference=payload.provider_reference,
            attempt_number=last_attempt + 1,
        )
        session.add(payment)
        await session.flush()
    else:
        if payment.status is PaymentStatus.SUCCEEDED and not payload.simulate_failure:
            return payment
        payment.attempt_number += 1

    if payload.simulate_failure:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "simulated_gateway_failure"
        payment.error_code = "SIMULATED"
        await enqueue_event(
            session,
            deal_id=deal.id,
            event_type="payment.failure",
            payload={"payment_id": payment.id, "idempotency_key": payment.idempotency_key},
        )
        session.add(
            AuditLog(
                deal_id=deal.id,
                actor="system",
                action="payment.failed",
                category=AuditCategory.PAYMENT,
                details={"payment_id": payment.id, "reason": payment.failure_reason},
                critical=True,
            )
        )
        if payload.simulate_rollback:
            payment.status = PaymentStatus.ROLLED_BACK
            payment.rolled_back_at = now
            await enqueue_event(
                session,
                deal_id=deal.id,
                event_type="payment.rollback",
                payload={"payment_id": payment.id},
            )
        return payment

    if payment.status is PaymentStatus.FAILED:
        payment.auto_recovered = True

    payment.status = PaymentStatus.SUCCEEDED
    payment.completed_at = now
    payment.failure_reason = None
    payment.error_code = None

    await enqueue_event(
        session,
        deal_id=deal.id,
        event_type="payment.succeeded",
        payload={
            "payment_id": payment.id,
            "idempotency_key": payment.idempotency_key,
            "amount": float(payment.amount),
        },
    )

    session.add(
        AuditLog(
            deal_id=deal.id,
            actor="system",
            action="payment.succeeded",
            category=AuditCategory.PAYMENT,
            details={"payment_id": payment.id},
            critical=False,
        )
    )

    deal.payment_collected_at = now
    await _mark_collection(deal, session, actor="system")
    return payment
