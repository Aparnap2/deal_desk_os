"""
SLA and KPI validation tests for Deal Desk OS.

This module tests:
- Five-minute touch rate compliance
- Quote-to-cash time measurements
- Idempotency error rate validation (< 0.5% target)
- Guardrail compliance rate testing
- Financial impact calculations
- Performance benchmarking
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import statistics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_

from app.models.deal import Deal, DealStage, DealRisk
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy
from app.services.sla_analytics import SLAAnalytics
from app.services.sla_cache import SLACache
from app.services.guardrail_service import evaluate_pricing_guardrails


class TestTouchRateSLA:
    """Testing five-minute touch rate SLA compliance."""

    @pytest_asyncio.asyncio
    async def test_five_minute_touch_rate_calculation(self, async_db_session, seed_test_data):
        """Test calculation of touch rate within 5-minute SLA."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Get deals created in last 24 hours
        since = datetime.utcnow() - timedelta(hours=24)
        touch_rate = await sla_analytics.calculate_touch_rate(
            since_datetime=since,
            touch_window_minutes=5
        )

        # Validate calculation method
        assert isinstance(touch_rate, dict)
        assert "total_deals" in touch_rate
        assert "touched_deals" in touch_rate
        assert "touch_rate_percentage" in touch_rate
        assert "within_sla" in touch_rate

        # Touch rate should be realistic (0-100%)
        assert 0 <= touch_rate["touch_rate_percentage"] <= 100

    @pytest_asyncio.asyncio
    async def test_touch_rate_target_validation(self, async_db_session):
        """Test that touch rate meets the 95% SLA target."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create test deals with controlled touch timestamps
        test_time = datetime.utcnow()
        deals_data = []

        for i in range(100):
            # 95 deals touched within 5 minutes, 5 not touched
            if i < 95:
                first_touch = test_time + timedelta(minutes=i % 5)
            else:
                first_touch = test_time + timedelta(minutes=10 + i)

            deals_data.append({
                "id": f"touch_test_deal_{i}",
                "name": f"Touch Test Deal {i}",
                "created_at": test_time,
                "first_touch_at": first_touch,
            })

        # Mock query results
        with patch.object(sla_analytics, '_get_deals_with_touch_times') as mock_query:
            mock_query.return_value = deals_data

            touch_rate = await sla_analytics.calculate_touch_rate(
                since_datetime=test_time - timedelta(hours=1),
                touch_window_minutes=5
            )

            assert touch_rate["touch_rate_percentage"] >= 95.0
            assert touch_rate["within_sla"] is True

    @pytest_asyncio.asyncio
    async def test_touch_rate_alert_generation(self, async_db_session):
        """Test alert generation when touch rate falls below threshold."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create scenario with low touch rate
        low_touch_data = [
            {"id": f"deal_{i}", "created_at": datetime.utcnow(), "first_touch_at": None}
            for i in range(50)
        ]

        with patch.object(sla_analytics, '_get_deals_with_touch_times') as mock_query:
            mock_query.return_value = low_touch_data

            alerts = await sla_analytics.generate_touch_rate_alerts(
                target_percentage=95.0,
                since_datetime=datetime.utcnow() - timedelta(hours=1)
            )

            assert len(alerts) > 0
            assert any(alert["type"] == "touch_rate_breach" for alert in alerts)
            assert alerts[0]["current_rate"] < 95.0


class TestQuoteToCashTimeValidation:
    """Testing quote-to-cash time measurement and validation."""

    @pytest_asyncio.asyncio
    async def test_qtc_time_calculation(self, async_db_session):
        """Test accurate calculation of quote-to-cash time."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create test deals with known timestamps
        test_deals = []
        base_time = datetime.utcnow() - timedelta(days=30)

        for i in range(10):
            created_at = base_time + timedelta(days=i)
            closed_at = created_at + timedelta(days=7 + (i % 10))  # 7-16 day cycles

            test_deals.append({
                "id": f"qtc_deal_{i}",
                "created_at": created_at,
                "closed_at": closed_at,
                "amount": Decimal("10000.00"),
                "stage": DealStage.CLOSED_WON,
            })

        with patch.object(sla_analytics, '_get_closed_deals') as mock_query:
            mock_query.return_value = test_deals

            qtc_metrics = await sla_analytics.calculate_qtc_metrics(
                since_datetime=base_time,
                target_days=10
            )

            assert "average_qtc_days" in qtc_metrics
            assert "median_qtc_days" in qtc_metrics
            assert "within_target_percentage" in qtc_metrics
            assert "total_deals" in qtc_metrics

            # Verify calculations
            assert qtc_metrics["average_qtc_days"] > 0
            assert qtc_metrics["median_qtc_days"] > 0
            assert 0 <= qtc_metrics["within_target_percentage"] <= 100

    @pytest_asyncio.asyncio
    async def test_qtc_time_distribution_analysis(self, async_db_session):
        """Test distribution analysis of quote-to-cash times."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create deals with varied QTC times
        test_deals = []
        base_time = datetime.utcnow() - timedelta(days=30)
        qtc_times = [5, 7, 8, 10, 12, 15, 20, 25, 30, 45]  # Days

        for i, qtc_days in enumerate(qtc_times):
            created_at = base_time + timedelta(days=i)
            closed_at = created_at + timedelta(days=qtc_days)

            test_deals.append({
                "id": f"distribution_deal_{i}",
                "created_at": created_at,
                "closed_at": closed_at,
                "amount": Decimal("10000.00"),
                "stage": DealStage.CLOSED_WON,
            })

        with patch.object(sla_analytics, '_get_closed_deals') as mock_query:
            mock_query.return_value = test_deals

            distribution = await sla_analytics.analyze_qtc_time_distribution(
                since_datetime=base_time
            )

            assert "percentiles" in distribution
            assert "buckets" in distribution
            assert "outliers" in distribution

            # Check percentiles
            percentiles = distribution["percentiles"]
            assert percentiles["p50"] == 11.0  # Median of [5,7,8,10,12,15,20,25,30,45]
            assert percentiles["p90"] >= 25
            assert percentiles["p95"] >= 30

    @pytest_asyncio.asyncio
    async def test_qtc_time_by_deal_size(self, async_db_session):
        """Test QTC time analysis segmented by deal size."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create deals of different sizes
        test_deals = []
        base_time = datetime.utcnow() - timedelta(days=30)

        deal_sizes = [
            (5000, 5),   # Small deals: faster
            (25000, 10), # Medium deals: standard
            (100000, 20),# Large deals: slower
        ]

        for size, qtc_days in deal_sizes:
            for i in range(10):
                created_at = base_time + timedelta(days=i)
                closed_at = created_at + timedelta(days=qtc_days + (i % 3))

                test_deals.append({
                    "id": f"size_deal_{size}_{i}",
                    "amount": Decimal(str(size)),
                    "created_at": created_at,
                    "closed_at": closed_at,
                    "stage": DealStage.CLOSED_WON,
                })

        with patch.object(sla_analytics, '_get_closed_deals') as mock_query:
            mock_query.return_value = test_deals

            size_analysis = await sla_analytics.analyze_qtc_by_deal_size(
                since_datetime=base_time,
                size_brackets=[(0, 10000), (10000, 50000), (50000, float('inf'))]
            )

            assert "size_brackets" in size_analysis
            assert len(size_analysis["size_brackets"]) == 3

            # Verify larger deals take longer on average
            brackets = size_analysis["size_brackets"]
            small_avg = brackets[0]["average_qtc_days"]
            large_avg = brackets[2]["average_qtc_days"]
            assert large_avg > small_avg


class TestIdempotencyErrorRate:
    """Testing idempotency error rate validation (< 0.5% target)."""

    @pytest_asyncio.asyncio
    async def test_idempotency_error_rate_calculation(self, async_db_session):
        """Test calculation of idempotency-related error rates."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create test payment data with controlled error rates
        test_payments = []
        base_time = datetime.utcnow() - timedelta(hours=24)

        # 1000 payments with 4 idempotency errors (0.4% error rate)
        for i in range(1000):
            payment_data = {
                "id": f"payment_{i}",
                "created_at": base_time + timedelta(minutes=i),
                "status": PaymentStatus.SUCCEEDED,
                "error_type": None,
            }

            # Insert idempotency errors
            if i in [100, 300, 600, 900]:
                payment_data.update({
                    "status": PaymentStatus.FAILED,
                    "error_type": "idempotency_conflict",
                })

            test_payments.append(payment_data)

        with patch.object(sla_analytics, '_get_payments_with_errors') as mock_query:
            mock_query.return_value = test_payments

            error_metrics = await sla_analytics.calculate_idempotency_error_rate(
                since_datetime=base_time
            )

            assert "total_payments" in error_metrics
            assert "idempotency_errors" in error_metrics
            assert "error_rate_percentage" in error_metrics
            assert "within_sla" in error_metrics

            assert error_metrics["total_payments"] == 1000
            assert error_metrics["idempotency_errors"] == 4
            assert error_metrics["error_rate_percentage"] == 0.4
            assert error_metrics["within_sla"] is True  # Below 0.5% target

    @pytest_asyncio.asyncio
    async def test_idempotency_error_breach_alert(self, async_db_session):
        """Test alert generation when idempotency error rate exceeds threshold."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create scenario with high error rate (1% - above 0.5% threshold)
        test_payments = []
        base_time = datetime.utcnow() - timedelta(hours=24)

        for i in range(100):
            payment_data = {
                "id": f"payment_breach_{i}",
                "created_at": base_time + timedelta(minutes=i),
                "status": PaymentStatus.SUCCEEDED,
                "error_type": None,
            }

            # 1% error rate
            if i % 100 == 0:
                payment_data.update({
                    "status": PaymentStatus.FAILED,
                    "error_type": "idempotency_conflict",
                })

            test_payments.append(payment_data)

        with patch.object(sla_analytics, '_get_payments_with_errors') as mock_query:
            mock_query.return_value = test_payments

            alerts = await sla_analytics.generate_idempotency_alerts(
                threshold_percentage=0.5,
                since_datetime=base_time
            )

            assert len(alerts) > 0
            assert any(alert["type"] == "idempotency_error_breach" for alert in alerts)
            assert alerts[0]["error_rate"] > 0.5

    @pytest_asyncio.asyncio
    async def test_idempotency_error_patterns(self, async_db_session):
        """Test analysis of idempotency error patterns."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create payments with different error patterns
        test_payments = []
        base_time = datetime.utcnow() - timedelta(hours=24)

        error_scenarios = [
            ("idempotency_conflict", 50),  # Most common
            ("duplicate_key", 20),
            ("concurrent_modification", 15),
            ("transaction_timeout", 10),
        ]

        for error_type, count in error_scenarios:
            for i in range(count):
                test_payments.append({
                    "id": f"payment_{error_type}_{i}",
                    "created_at": base_time + timedelta(minutes=i),
                    "status": PaymentStatus.FAILED,
                    "error_type": error_type,
                })

        with patch.object(sla_analytics, '_get_payments_with_errors') as mock_query:
            mock_query.return_value = test_payments

            pattern_analysis = await sla_analytics.analyze_idempotency_error_patterns(
                since_datetime=base_time
            )

            assert "error_types" in pattern_analysis
            assert "recommendations" in pattern_analysis

            # Verify most common error identified
            error_types = pattern_analysis["error_types"]
            assert error_types[0]["error_type"] == "idempotency_conflict"
            assert error_types[0]["count"] == 50


class TestGuardrailComplianceRate:
    """Testing guardrail compliance rate validation."""

    @pytest_asyncio.asyncio
    async def test_guardrail_compliance_calculation(self, async_db_session, test_policy):
        """Test calculation of guardrail compliance rates."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create test deals with guardrail results
        test_deals = []
        base_time = datetime.utcnow() - timedelta(days=30)

        for i in range(100):
            # 90% compliance rate
            passed_guardrails = i < 90

            deal_data = {
                "id": f"guardrail_deal_{i}",
                "created_at": base_time + timedelta(hours=i),
                "amount": Decimal("10000.00"),
                "guardrail_result": {
                    "passed": passed_guardrails,
                    "violations": [] if passed_guardrails else [{"type": "discount_limit"}],
                }
            }
            test_deals.append(deal_data)

        with patch.object(sla_analytics, '_get_deals_with_guardrail_results') as mock_query:
            mock_query.return_value = test_deals

            compliance_metrics = await sla_analytics.calculate_guardrail_compliance(
                since_datetime=base_time,
                policy_id=test_policy.id
            )

            assert "total_deals" in compliance_metrics
            assert "compliant_deals" in compliance_metrics
            assert "compliance_rate" in compliance_metrics
            assert "within_sla" in compliance_metrics

            assert compliance_metrics["total_deals"] == 100
            assert compliance_metrics["compliant_deals"] == 90
            assert compliance_metrics["compliance_rate"] == 0.9
            assert compliance_metrics["within_sla"] is True  # Assuming 90% is target

    @pytest_asyncio.asyncio
    async def test_guardrail_violation_analysis(self, async_db_session):
        """Test analysis of guardrail violations by type."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create deals with different violation types
        violation_types = ["discount_limit", "payment_terms", "price_floor", "risk_mismatch"]
        test_deals = []

        for i, violation_type in enumerate(violation_types * 10):  # 10 of each type
            deal_data = {
                "id": f"violation_deal_{i}",
                "created_at": datetime.utcnow() - timedelta(hours=i),
                "amount": Decimal("10000.00"),
                "guardrail_result": {
                    "passed": False,
                    "violations": [{"type": violation_type, "severity": "high" if i % 2 == 0 else "medium"}],
                }
            }
            test_deals.append(deal_data)

        with patch.object(sla_analytics, '_get_deals_with_guardrail_results') as mock_query:
            mock_query.return_value = test_deals

            violation_analysis = await sla_analytics.analyze_guardrail_violations(
                since_datetime=datetime.utcnow() - timedelta(days=1)
            )

            assert "violation_types" in violation_analysis
            assert "severity_distribution" in violation_analysis
            assert "trending" in violation_analysis

            # Verify all violation types captured
            types = [v["type"] for v in violation_analysis["violation_types"]]
            for violation_type in violation_types:
                assert violation_type in types

    @pytest_asyncio.asyncio
    async def test_guardrail_effectiveness_measurement(self, async_db_session):
        """Test measurement of guardrail effectiveness in preventing issues."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Mock data showing deals that passed guardrails vs those that didn't
        effectiveness_data = [
            {
                "passed_guardrails": True,
                "had_payment_issues": False,
                "required_manual_review": False,
            },
            {
                "passed_guardrails": False,
                "had_payment_issues": True,
                "required_manual_review": True,
            }
        ] * 50  # 100 total records

        with patch.object(sla_analytics, '_get_deal_effectiveness_data') as mock_query:
            mock_query.return_value = effectiveness_data

            effectiveness = await sla_analytics.measure_guardrail_effectiveness(
                since_datetime=datetime.utcnow() - timedelta(days=30)
            )

            assert "issue_prevention_rate" in effectiveness
            assert "manual_review_reduction" in effectiveness
            assert "roi_metrics" in effectiveness

            # Guardrails should prevent issues
            assert effectiveness["issue_prevention_rate"] > 0


class TestFinancialImpactCalculations:
    """Testing financial impact calculation accuracy."""

    @pytest_asyncio.asyncio
    async def test_policy_change_financial_impact(self, async_db_session):
        """Test financial impact calculation for policy changes."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Create test deals for impact simulation
        test_deals = []
        for i in range(50):
            test_deals.append({
                "id": f"impact_deal_{i}",
                "name": f"Impact Test Deal {i}",
                "amount": Decimal(str(10000 + (i * 1000))),
                "discount_percent": Decimal("15.0"),
                "risk": "low" if i % 3 == 0 else "medium",
                "payment_terms_days": 30,
            })

        # Test policy change: reduce max discount from 25% to 20%
        old_policy_config = {
            "discount_guardrails": {"default_max_discount_percent": 25},
            "payment_terms_guardrails": {"max_terms_days": 60},
        }

        new_policy_config = {
            "discount_guardrails": {"default_max_discount_percent": 20},
            "payment_terms_guardrails": {"max_terms_days": 45},
        }

        with patch.object(sla_analytics, '_simulate_policy_impact') as mock_simulate:
            mock_simulate.return_value = {
                "total_deals": 50,
                "affected_deals": 15,
                "revenue_impact": Decimal("75000.00"),
                "approval_required_deals": 8,
                "estimated_approval_delay_days": 3,
            }

            impact_analysis = await sla_analytics.calculate_policy_financial_impact(
                deals=test_deals,
                old_policy=old_policy_config,
                new_policy=new_policy_config
            )

            assert "revenue_impact" in impact_analysis
            assert "operational_impact" in impact_analysis
            assert "risk_assessment" in impact_analysis

            # Revenue impact should be positive for stricter discount policy
            assert impact_analysis["revenue_impact"]["total_increase"] > 0

    @pytest_asyncio.asyncio
    async def test_sla_breach_financial_cost(self, async_db_session):
        """Test calculation of financial cost of SLA breaches."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Mock SLA breach data
        breach_data = [
            {
                "breach_type": "touch_rate",
                "affected_deals": 25,
                "average_deal_size": Decimal("15000.00"),
                "probability_impact": 0.1,  # 10% lower close probability
                "delay_cost_per_day": Decimal("100.00"),
                "average_delay_days": 5,
            },
            {
                "breach_type": "qtc_time",
                "affected_deals": 15,
                "average_deal_size": Decimal("25000.00"),
                "delay_cost_per_day": Decimal("200.00"),
                "average_delay_days": 10,
            }
        ]

        with patch.object(sla_analytics, '_get_sla_breach_data') as mock_query:
            mock_query.return_value = breach_data

            cost_analysis = await sla_analytics.calculate_sla_breach_costs(
                since_datetime=datetime.utcnow() - timedelta(days=30)
            )

            assert "total_financial_impact" in cost_analysis
            assert "breakdown_by_breach_type" in cost_analysis
            assert "opportunity_cost" in cost_analysis

            # Should calculate meaningful financial impact
            assert cost_analysis["total_financial_impact"] > 0

    @pytest_asyncio.asyncio
    async def test_roi_calculation_for_improvements(self, async_db_session):
        """Test ROI calculation for SLA and guardrail improvements."""
        sla_analytics = SLAAnalytics(async_db_session)

        # Investment and return data
        investment_scenarios = [
            {
                "initiative": "touch_rate_automation",
                "investment_cost": Decimal("50000.00"),
                "expected_touch_rate_improvement": 0.15,  # 15% improvement
                "affected_deals_per_month": 100,
                "average_deal_value": Decimal("12000.00"),
            },
            {
                "initiative": "guardrail_optimization",
                "investment_cost": Decimal("30000.00"),
                "expected_compliance_improvement": 0.10,  # 10% improvement
                "error_reduction_rate": 0.20,  # 20% fewer errors
                "average_error_cost": Decimal("500.00"),
            }
        ]

        roi_analysis = await sla_analytics.calculate_improvement_roi(
            scenarios=investment_scenarios,
            analysis_period_months=12
        )

        assert "initiatives" in roi_analysis
        assert "total_investment" in roi_analysis
        assert "total_return" in roi_analysis
        assert "overall_roi_percentage" in roi_analysis

        # Should identify positive ROI initiatives
        assert len(roi_analysis["initiatives"]) > 0
        assert roi_analysis["overall_roi_percentage"] > 0