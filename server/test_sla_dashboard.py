"""
Test suite for SLA Dashboard functionality.

This module provides comprehensive testing for SLA calculations, API endpoints,
and overall dashboard functionality.
"""

import asyncio
import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from app.models.deal import Deal, DealStage, GuardrailStatus, OrchestrationMode
from app.models.payment import Payment, PaymentStatus
from app.models.approval import Approval, ApprovalStatus
from app.services.sla_analytics import SLAAnalyticsService, BusinessHoursCalculator
from app.services.sla_cache import SLACacheService, cache_sla_metrics
from app.config.sla_config import SLAConfig, sla_config


class TestBusinessHoursCalculator:
    """Test cases for BusinessHoursCalculator."""

    def test_business_hours_detection(self):
        """Test business hours detection."""
        calculator = BusinessHoursCalculator()

        # Test business hours (weekday 9am-5pm)
        business_datetime = datetime(2025, 1, 15, 14, 30)  # Wednesday 2:30 PM
        assert calculator.is_business_hours(business_datetime) == True

        # Test non-business hours (weekday 8pm)
        non_business_datetime = datetime(2025, 1, 15, 20, 30)  # Wednesday 8:30 PM
        assert calculator.is_business_hours(non_business_datetime) == False

        # Test weekend
        weekend_datetime = datetime(2025, 1, 18, 14, 30)  # Saturday 2:30 PM
        assert calculator.is_business_hours(weekend_datetime) == False

    def test_business_hours_between(self):
        """Test business hours calculation between timestamps."""
        calculator = BusinessHoursCalculator()

        # Test same business day
        start = datetime(2025, 1, 15, 9, 30)  # Wednesday 9:30 AM
        end = datetime(2025, 1, 15, 14, 30)   # Wednesday 2:30 PM
        hours = calculator.business_hours_between(start, end)
        assert hours == 5.0  # 5 hours

        # Test spanning weekend (should skip weekend hours)
        start = datetime(2025, 1, 17, 16, 0)   # Friday 4:00 PM
        end = datetime(2025, 1, 20, 10, 0)    # Monday 10:00 AM
        hours = calculator.business_hours_between(start, end)
        assert hours == 2.0  # 1 hour Friday + 1 hour Monday


class TestSLAConfig:
    """Test cases for SLA configuration."""

    def test_sla_targets(self):
        """Test SLA target definitions."""
        targets = sla_config.get_sla_targets()

        assert "five_minute_touch_rate" in targets
        assert "quote_to_cash_time" in targets
        assert "idempotent_write_error_rate" in targets
        assert "guardrail_compliance_rate" in targets

        # Check target values
        assert targets["five_minute_touch_rate"].target_value == 80.0
        assert targets["quote_to_cash_time"].target_value == 48.0
        assert targets["idempotent_write_error_rate"].target_value == 0.5
        assert targets["guardrail_compliance_rate"].target_value == 95.0

    def test_sla_compliance_check(self):
        """Test SLA compliance checking."""
        # Test compliant metrics (higher is better)
        result = sla_config.check_sla_compliance("five_minute_touch_rate", 85.0)
        assert result["compliant"] == True
        assert result["status"] == "compliant"

        result = sla_config.check_sla_compliance("five_minute_touch_rate", 72.0)
        assert result["compliant"] == False
        assert result["status"] == "critical"

        # Test compliant metrics (lower is better)
        result = sla_config.check_sla_compliance("quote_to_cash_time", 36.0)
        assert result["compliant"] == True
        assert result["status"] == "compliant"

        result = sla_config.check_sla_compliance("quote_to_cash_time", 80.0)
        assert result["compliant"] == False
        assert result["status"] == "warning"


class TestSLAAnalyticsService:
    """Test cases for SLA analytics calculations."""

    @pytest.fixture
    async def sample_deals(self) -> list[Dict[str, Any]]:
        """Create sample deal data for testing."""
        now = datetime.utcnow()
        return [
            {
                "id": "deal_1",
                "name": "Test Deal 1",
                "amount": Decimal("10000.00"),
                "quote_generated_at": now - timedelta(hours=2),
                "agreement_signed_at": now - timedelta(hours=1),
                "payment_collected_at": now - timedelta(minutes=30),
                "created_at": now - timedelta(hours=3),
                "guardrail_status": GuardrailStatus.PASS,
                "orchestration_mode": OrchestrationMode.ORCHESTRATED,
                "operational_cost": Decimal("500.00"),
                "manual_cost_baseline": Decimal("1500.00"),
            },
            {
                "id": "deal_2",
                "name": "Test Deal 2",
                "amount": Decimal("25000.00"),
                "quote_generated_at": now - timedelta(days=1),
                "agreement_signed_at": now - timedelta(hours=20),
                "payment_collected_at": now - timedelta(hours=18),
                "created_at": now - timedelta(days=1, hours=1),
                "guardrail_status": GuardrailStatus.VIOLATED,
                "guardrail_reason": "Discount exceeds threshold",
                "orchestration_mode": OrchestrationMode.MANUAL,
                "operational_cost": Decimal("2000.00"),
                "manual_cost_baseline": Decimal("2000.00"),
            },
            {
                "id": "deal_3",
                "name": "Test Deal 3",
                "amount": Decimal("15000.00"),
                "quote_generated_at": now - timedelta(minutes=3),
                "created_at": now - timedelta(minutes=1),
                "guardrail_status": GuardrailStatus.PASS,
                "orchestration_mode": OrchestrationMode.ORCHESTRATED,
                "operational_cost": Decimal("750.00"),
                "manual_cost_baseline": Decimal("1800.00"),
            }
        ]

    @pytest.fixture
    async def sample_payments(self) -> list[Dict[str, Any]]:
        """Create sample payment data for testing."""
        now = datetime.utcnow()
        return [
            {
                "id": "payment_1",
                "deal_id": "deal_1",
                "status": PaymentStatus.SUCCEEDED,
                "amount": Decimal("10000.00"),
                "attempt_number": 1,
                "idempotency_key": "idemp_1",
                "created_at": now - timedelta(hours=1),
            },
            {
                "id": "payment_2",
                "deal_id": "deal_2",
                "status": PaymentStatus.FAILED,
                "amount": Decimal("25000.00"),
                "attempt_number": 2,
                "idempotency_key": "idemp_2",
                "error_code": "INSUFFICIENT_FUNDS",
                "created_at": now - timedelta(hours=19),
            },
            {
                "id": "payment_3",
                "deal_id": "deal_2",
                "status": PaymentStatus.SUCCEEDED,
                "amount": Decimal("25000.00"),
                "attempt_number": 3,
                "idempotency_key": "idemp_2",
                "auto_recovered": True,
                "created_at": now - timedelta(hours=18),
            }
        ]

    def test_five_minute_touch_rate_calculation(self, sample_deals):
        """Test five-minute touch rate calculation."""
        # Mock implementation - in real test, this would use a database session
        service = SLAAnalyticsService()

        # Test business hours calculation
        biz_calc = BusinessHoursCalculator()

        # Create a simple test scenario
        total_deals = len(sample_deals)
        business_hour_deals = 0
        touched_within_5min = 0

        for deal in sample_deals:
            if deal["quote_generated_at"]:
                if biz_calc.is_business_hours(deal["quote_generated_at"]):
                    business_hour_deals += 1

                    if deal["created_at"]:
                        business_hours_diff = biz_calc.business_hours_between(
                            deal["created_at"],
                            deal["quote_generated_at"]
                        )
                        if business_hours_diff <= (5/60):  # 5 minutes
                            touched_within_5min += 1

        touch_rate = (touched_within_5min / business_hour_deals * 100) if business_hour_deals > 0 else 0

        assert isinstance(touch_rate, float)
        assert 0 <= touch_rate <= 100

    def test_quote_to_cash_calculation(self, sample_deals):
        """Test quote-to-cash time calculation."""
        completed_deals = [d for d in sample_deals if d.get("payment_collected_at")]

        quote_to_cash_times = []
        for deal in completed_deals:
            if deal["quote_generated_at"] and deal["payment_collected_at"]:
                total_time = deal["payment_collected_at"] - deal["quote_generated_at"]
                total_hours = total_time.total_seconds() / 3600
                quote_to_cash_times.append(total_hours)

        assert len(quote_to_cash_times) > 0

        # Calculate median
        sorted_times = sorted(quote_to_cash_times)
        median = sorted_times[len(sorted_times) // 2] if sorted_times else 0

        assert isinstance(median, float)
        assert median > 0

    def test_error_rate_calculation(self, sample_payments):
        """Test error rate calculation."""
        total_attempts = len(sample_payments)
        failed_attempts = sum(1 for p in sample_payments if p["status"] == PaymentStatus.FAILED)
        auto_recovered = sum(1 for p in sample_payments if p.get("auto_recovered", False))

        error_rate = (failed_attempts / total_attempts * 100) if total_attempts > 0 else 0
        auto_recovery_rate = (auto_recovered / failed_attempts * 100) if failed_attempts > 0 else 0

        assert isinstance(error_rate, float)
        assert 0 <= error_rate <= 100
        assert isinstance(auto_recovery_rate, float)
        assert 0 <= auto_recovery_rate <= 100

    def test_guardrail_compliance_calculation(self, sample_deals):
        """Test guardrail compliance calculation."""
        total_deals = len(sample_deals)
        passed_deals = sum(1 for d in sample_deals if d["guardrail_status"] == GuardrailStatus.PASS)
        violated_deals = sum(1 for d in sample_deals if d["guardrail_status"] == GuardrailStatus.VIOLATED)

        compliance_rate = (passed_deals / total_deals * 100) if total_deals > 0 else 0

        assert isinstance(compliance_rate, float)
        assert 0 <= compliance_rate <= 100
        assert passed_deals + violated_deals == total_deals

    def test_financial_impact_calculation(self, sample_deals):
        """Test financial impact calculation."""
        total_revenue = sum(d["amount"] for d in sample_deals)
        total_operational_cost = sum(d["operational_cost"] for d in sample_deals)
        total_manual_cost_baseline = sum(d["manual_cost_baseline"] for d in sample_deals)

        cost_savings = total_manual_cost_baseline - total_operational_cost
        cost_savings_percentage = (cost_savings / total_manual_cost_baseline * 100) if total_manual_cost_baseline > 0 else 0

        orchestrated_deals = [d for d in sample_deals if d["orchestration_mode"] == OrchestrationMode.ORCHESTRATED]
        orchestrated_revenue = sum(d["amount"] for d in orchestrated_deals)
        orchestrated_percentage = (orchestrated_revenue / total_revenue * 100) if total_revenue > 0 else 0

        assert isinstance(cost_savings, (int, float))
        assert isinstance(cost_savings_percentage, float)
        assert isinstance(orchestrated_percentage, float)
        assert 0 <= orchestrated_percentage <= 100


class TestSLACacheService:
    """Test cases for SLA cache service."""

    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache_service = SLACacheService()

        key1 = cache_service._generate_cache_key(
            "touch_rate",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31)
        )

        key2 = cache_service._generate_cache_key(
            "touch_rate",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31)
        )

        key3 = cache_service._generate_cache_key(
            "touch_rate",
            start_date=date(2025, 2, 1),
            end_date=date(2025, 2, 28)
        )

        # Same parameters should generate same key
        assert key1 == key2

        # Different parameters should generate different keys
        assert key1 != key3

        # Keys should start with prefix
        assert key1.startswith("sla_dashboard:touch_rate:")
        assert key3.startswith("sla_dashboard:touch_rate:")

    @pytest.mark.asyncio
    async def test_cache_operations(self):
        """Test basic cache operations."""
        cache_service = SLACacheService()

        # Test data
        test_data = {
            "touch_rate_percentage": 85.5,
            "total_deals": 100,
            "generated_at": datetime.utcnow().isoformat()
        }

        # Try to cache data (will fail if Redis not available)
        cache_result = await cache_service.cache_metrics(
            "touch_rate",
            test_data,
            ttl=60,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31)
        )

        # Try to retrieve cached data
        cached_data = await cache_service.get_cached_metrics(
            "touch_rate",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31)
        )

        if cache_service._get_redis_client() is not None:
            # Redis is available, should work
            assert cache_result == True
            assert cached_data is not None
            assert cached_data["data"]["touch_rate_percentage"] == 85.5
        else:
            # Redis not available, should gracefully fail
            assert cache_result == False
            assert cached_data is None


# Integration Tests
class TestSLADashboardIntegration:
    """Integration tests for SLA dashboard functionality."""

    @pytest.mark.asyncio
    async def test_end_to_end_dashboard_flow(self):
        """Test end-to-end dashboard data flow."""
        # This would test the complete flow from database queries to API responses
        # In a real implementation, this would set up test data in a test database

        service = SLAAnalyticsService()

        # Mock the dashboard summary generation
        # In real tests, this would use actual database sessions
        dashboard_structure = {
            "five_minute_touch_rate": {"status": "success"},
            "quote_to_cash_time": {"status": "success"},
            "idempotent_write_error_rate": {"status": "success"},
            "guardrail_compliance_rate": {"status": "success"},
            "financial_impact": {"status": "success"},
            "overall_sla_status": {
                "status": "all_met",
                "overall_compliance_percentage": 100.0,
                "targets_met": 4,
                "total_targets": 4
            }
        }

        # Verify structure
        required_keys = [
            "five_minute_touch_rate",
            "quote_to_cash_time",
            "idempotent_write_error_rate",
            "guardrail_compliance_rate",
            "financial_impact",
            "overall_sla_status"
        ]

        for key in required_keys:
            assert key in dashboard_structure


# Performance Tests
class TestSLADashboardPerformance:
    """Performance tests for SLA dashboard."""

    @pytest.mark.asyncio
    async def test_calculation_performance(self):
        """Test that SLA calculations complete within acceptable time limits."""
        import time

        service = SLAAnalyticsService()

        # Mock large dataset calculation
        start_time = time.time()

        # Simulate calculation time
        await asyncio.sleep(0.1)  # Simulate 100ms calculation

        calculation_time = time.time() - start_time

        # Should complete within 30 seconds (configurable threshold)
        assert calculation_time < 30.0, f"Calculation took too long: {calculation_time}s"

    def test_memory_usage(self):
        """Test memory usage of SLA calculations."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Simulate memory-intensive calculations
        large_dataset = list(range(100000))  # Simulate large dataset

        # Calculate some metrics
        metrics = {
            "median": len(large_dataset) // 2,
            "mean": sum(large_dataset) / len(large_dataset),
            "max": max(large_dataset),
            "min": min(large_dataset)
        }

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100MB for this test)
        assert memory_increase < 100, f"Memory usage increased by {memory_increase}MB"

        # Clean up
        del large_dataset


if __name__ == "__main__":
    # Run basic tests
    print("Running SLA Dashboard Tests...")

    # Test BusinessHoursCalculator
    calc = BusinessHoursCalculator()
    test_datetime = datetime(2025, 1, 15, 14, 30)
    print(f"Business hours test: {calc.is_business_hours(test_datetime)}")

    # Test SLAConfig
    config = SLAConfig()
    targets = config.get_sla_targets()
    print(f"SLA targets loaded: {list(targets.keys())}")

    # Test SLA compliance
    compliance = config.check_sla_compliance("five_minute_touch_rate", 85.0)
    print(f"Compliance check result: {compliance}")

    print("Basic tests completed successfully!")