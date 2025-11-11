from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus

POLICY_PATH = Path(__file__).resolve().parents[3] / "shared" / "policies" / "pricing_policy_v1.json"


@lru_cache
def load_pricing_policy() -> dict[str, Any]:
    with POLICY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(slots=True)
class GuardrailEvaluation:
    status: GuardrailStatus
    reason: str | None = None
    required_stage: DealStage | None = None
    requires_manual_review: bool = False


def _resolve_risk(risk: DealRisk | str | None) -> DealRisk:
    if isinstance(risk, DealRisk):
        return risk
    if isinstance(risk, str):
        return DealRisk(risk)
    return DealRisk.MEDIUM


def evaluate_pricing_guardrails(
    *,
    amount: float,
    discount_percent: float,
    payment_terms_days: int,
    risk: DealRisk | str | None,
) -> GuardrailEvaluation:
    policy = load_pricing_policy()
    guardrails = policy["discount_guardrails"]
    payment_policy = policy["payment_terms_guardrails"]
    price_floor = policy["price_floor"]

    resolved_risk = _resolve_risk(risk)
    max_discount = guardrails["risk_overrides"].get(resolved_risk.value, guardrails["default_max_discount_percent"])
    if discount_percent > max_discount:
        return GuardrailEvaluation(
            status=GuardrailStatus.VIOLATED,
            reason=f"discount {discount_percent:.1f}% exceeds {max_discount:.1f}% limit for {resolved_risk.value} risk",
        )

    if amount < price_floor["min_amount"]:
        return GuardrailEvaluation(
            status=GuardrailStatus.VIOLATED,
            reason=f"amount ${amount:,.2f} is below configured floor ${price_floor['min_amount']:,.2f}",
        )

    if payment_terms_days > payment_policy["max_terms_days"]:
        return GuardrailEvaluation(
            status=GuardrailStatus.VIOLATED,
            reason=f"payment terms {payment_terms_days} days exceed {payment_policy['max_terms_days']} day limit",
        )

    requires_manual_review = False
    required_stage: DealStage | None = None

    if discount_percent > guardrails["requires_executive_approval_above"]:
        required_stage = DealStage.EXEC_APPROVAL
        requires_manual_review = True

    if payment_terms_days > payment_policy["requires_finance_review_above_days"]:
        required_stage = DealStage.FINANCE_REVIEW
        requires_manual_review = True

    return GuardrailEvaluation(
        status=GuardrailStatus.PASS,
        required_stage=required_stage,
        requires_manual_review=requires_manual_review,
    )


def apply_guardrail_result(deal: Deal, evaluation: GuardrailEvaluation) -> None:
    deal.guardrail_status = evaluation.status
    deal.guardrail_reason = evaluation.reason
    deal.guardrail_locked = evaluation.status is GuardrailStatus.VIOLATED
    if evaluation.required_stage and deal.stage != evaluation.required_stage:
        deal.stage = evaluation.required_stage
