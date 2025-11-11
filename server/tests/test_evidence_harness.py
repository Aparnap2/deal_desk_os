from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus, OrchestrationMode
from app.models.payment import Payment, PaymentStatus
from app.schemas.deal import DealCreate
from app.schemas.payment import PaymentCreate
from app.services.analytics_service import compute_dashboard_metrics
from app.services.deal_service import create_deal
from app.services.payment_service import process_payment
from app.services.outbox_service import dispatch_pending_events


@pytest.mark.asyncio
async def test_scope_to_cash_evidence_harness() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        await _simulate_deals(session)
        await session.commit()

        await dispatch_pending_events(session)
        await session.commit()

        metrics = await compute_dashboard_metrics(session)

        assert metrics.median_time_to_cash_hours <= 24
        assert metrics.guardrail_compliance_rate >= 80
        assert metrics.failure_auto_recovery_rate > 0

        deal_result = await session.execute(select(Deal.guardrail_status))
        guardrail_statuses = deal_result.scalars().all()
        assert guardrail_statuses.count(GuardrailStatus.VIOLATED) == 10

        payment_result = await session.execute(select(Payment.status))
        statuses = payment_result.scalars().all()
        assert statuses.count(PaymentStatus.FAILED) == 0
        assert statuses.count(PaymentStatus.ROLLED_BACK) == 0


async def _simulate_deals(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    terms = [30, 30, 45, 15, 20]
    discounts = [5, 10, 8, 9, 6]
    idempotency_seen: set[str] = set()

    for index in range(50):
        amount = Decimal("12000") + Decimal(index * 150)
        risk = DealRisk.LOW if index % 3 == 0 else (DealRisk.MEDIUM if index % 3 == 1 else DealRisk.HIGH)
        payment_terms = terms[index % len(terms)]
        discount = discounts[index % len(discounts)]

        if index >= 40:
            discount = 35
            payment_terms = 60

        deal = await create_deal(
            session,
            DealCreate(
                name=f"Deal {index}",
                description="Simulated revops scenario",
                amount=amount,
                currency="USD",
                stage=DealStage.PRICING,
                risk=risk,
                probability=75,
                expected_close=None,
                industry="software",
                owner_id=None,
                discount_percent=Decimal(discount),
                payment_terms_days=payment_terms,
                quote_generated_at=now - timedelta(hours=4),
                agreement_signed_at=None,
                payment_collected_at=None,
                orchestration_mode=OrchestrationMode.ORCHESTRATED,
                operational_cost=Decimal("85"),
                manual_cost_baseline=Decimal("260"),
                esign_envelope_id=None,
            ),
        )

        if deal.guardrail_status is GuardrailStatus.VIOLATED:
            continue

        idempotency_key = f"idem-{index:03d}"
        payment_request = PaymentCreate(
            amount=amount,
            currency="USD",
            idempotency_key=idempotency_key,
            provider_reference=f"sim-{index}",
            simulate_failure=index % 10 == 0,
            simulate_rollback=index % 20 == 0,
        )

        payment = await process_payment(session, deal=deal, payload=payment_request, redis_client=None)

        if payment.status in {PaymentStatus.FAILED, PaymentStatus.ROLLED_BACK}:
            retry_request = PaymentCreate(
                amount=amount,
                currency="USD",
                idempotency_key=idempotency_key,
                provider_reference=f"sim-{index}",
                simulate_failure=False,
                simulate_rollback=False,
            )
            payment = await process_payment(session, deal=deal, payload=retry_request, redis_client=None)

        assert payment.status is PaymentStatus.SUCCEEDED
        assert payment.idempotency_key not in idempotency_seen
        idempotency_seen.add(payment.idempotency_key)

        duplicate_call = await process_payment(
            session,
            deal=deal,
            payload=PaymentCreate(
                amount=amount,
                currency="USD",
                idempotency_key=idempotency_key,
                provider_reference=f"sim-{index}",
            ),
            redis_client=None,
        )
        assert duplicate_call.id == payment.id

    await session.flush()
