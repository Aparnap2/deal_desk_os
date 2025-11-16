from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.services.policy_service import PolicyService

POLICY_PATH = Path(__file__).resolve().parents[3] / "shared" / "policies" / "pricing_policy_v1.json"

# Global service instance - will be initialized when needed
_policy_service: Optional[PolicyService] = None
_db_session: Optional[Session] = None


def initialize_policy_service(db: Session) -> None:
    """Initialize the policy service with a database session"""
    global _policy_service, _db_session
    _db_session = db
    _policy_service = PolicyService(db)


@lru_cache
def load_pricing_policy() -> dict[str, Any]:
    """Load pricing policy - tries database first, falls back to JSON"""
    if _policy_service and _db_session:
        # Try to get active pricing policies from database
        try:
            active_policies = _policy_service.get_policies(
                policy_type=PolicyType.PRICING, status=PolicyStatus.ACTIVE
            )
            if active_policies:
                # Combine multiple policies if needed
                # For now, use the highest priority active policy
                policy = max(active_policies, key=lambda p: p.priority)
                return {
                    "version": policy.version,
                    "effective_at": policy.effective_at.isoformat() if policy.effective_at else None,
                    "discount_guardrails": policy.configuration.get("discount_guardrails", {}),
                    "payment_terms_guardrails": policy.configuration.get("payment_terms_guardrails", {}),
                    "price_floor": policy.configuration.get("price_floor", {}),
                }
        except Exception:
            # Fall back to JSON if database access fails
            pass

    # Fallback to JSON file
    if POLICY_PATH.exists():
        with POLICY_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)

    # Default fallback configuration
    return {
        "version": "1.0.0",
        "effective_at": "2025-01-01T00:00:00Z",
        "discount_guardrails": {
            "default_max_discount_percent": 25,
            "risk_overrides": {"low": 30, "medium": 20, "high": 10},
            "requires_executive_approval_above": 20,
        },
        "payment_terms_guardrails": {
            "max_terms_days": 45,
            "requires_finance_review_above_days": 30,
        },
        "price_floor": {"currency": "USD", "min_amount": 5000},
    }


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
