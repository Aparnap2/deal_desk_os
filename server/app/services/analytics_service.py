from __future__ import annotations

from statistics import median
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, GuardrailStatus
from app.models.payment import Payment
from app.schemas.analytics import DashboardMetrics, TotalCostOfOwnership


async def _load_deals(session: AsyncSession) -> Sequence[Deal]:
    result = await session.execute(select(Deal))
    return result.scalars().all()


async def _load_payments(session: AsyncSession) -> Sequence[Payment]:
    result = await session.execute(select(Payment))
    return result.scalars().all()


async def compute_dashboard_metrics(session: AsyncSession) -> DashboardMetrics:
    deals = await _load_deals(session)
    payments = await _load_payments(session)

    durations = [
        (deal.payment_collected_at - deal.quote_generated_at).total_seconds() / 3600
        for deal in deals
        if deal.quote_generated_at and deal.payment_collected_at
    ]

    compliance_total = len(deals)
    compliant = sum(1 for deal in deals if deal.guardrail_status is GuardrailStatus.PASS)
    compliance_rate = (compliant / compliance_total * 100) if compliance_total else 0

    total_payments = len(payments)
    auto_recovered = sum(1 for payment in payments if payment.auto_recovered)
    auto_recovery_rate = (auto_recovered / total_payments * 100) if total_payments else 0

    total_cost = sum(float(deal.operational_cost or 0) for deal in deals)
    manual_cost = sum(float(deal.manual_cost_baseline or 0) for deal in deals)
    avg_cost = (total_cost / compliance_total) if compliance_total else 0
    cost_per_100_deals = avg_cost * 100

    tco = TotalCostOfOwnership(
        manual=manual_cost,
        orchestrated=total_cost,
        delta=manual_cost - total_cost,
    )

    return DashboardMetrics(
        median_time_to_cash_hours=median(durations) if durations else 0,
        guardrail_compliance_rate=compliance_rate,
        failure_auto_recovery_rate=auto_recovery_rate,
        cost_per_100_deals=cost_per_100_deals,
        manual_vs_orchestrated_tco=tco,
    )
