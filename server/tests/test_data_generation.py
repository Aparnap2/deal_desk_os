"""
Test data generation utilities for comprehensive testing.

This module provides realistic test data for different scenarios:
- Realistic deal data sets
- Edge cases and error conditions
- Performance test data for load testing
- Compliance test scenarios
- Integration test data sets
"""

import random
import string
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional
from faker import Faker

# Initialize faker for realistic data generation
fake = Faker(['en_US', 'en_GB', 'de_DE', 'fr_FR'])


class DealDataGenerator:
    """Generator for realistic deal test data."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize with optional seed for reproducible data."""
        if seed:
            random.seed(seed)
            fake.seed_instance(seed)

    def generate_deal(
        self,
        deal_id: Optional[str] = None,
        amount_range: tuple = (5000, 500000),
        discount_range: tuple = (0, 30),
        custom_fields: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate a single realistic deal."""
        amount = random.uniform(*amount_range)
        discount = random.uniform(*discount_range)

        base_deal = {
            "id": deal_id or f"deal_{fake.uuid4()[:8]}",
            "name": self._generate_deal_name(),
            "description": fake.paragraph(nb_sentences=3),
            "amount": str(round(amount, 2)),
            "currency": random.choice(["USD", "EUR", "GBP", "CAD"]),
            "discount_percent": str(round(discount, 2)),
            "payment_terms_days": random.choice([15, 30, 45, 60, 90]),
            "risk": random.choice(["low", "medium", "high"]),
            "probability": random.randint(10, 95),
            "stage": random.choice([
                "prospecting", "qualification", "needs_analysis",
                "proposal", "negotiation", "closed_won", "closed_lost"
            ]),
            "industry": random.choice([
                "technology", "healthcare", "finance", "manufacturing",
                "retail", "education", "government", "non_profit"
            ]),
            "customer_size": random.choice(["small", "medium", "enterprise", "strategic"]),
            "region": random.choice(["americas", "emea", "apac"]),
            "sales_rep": fake.name(),
            "expected_close": (datetime.utcnow() + timedelta(days=random.randint(1, 180))).isoformat(),
            "created_at": fake.date_time_between(start_date="-2y", end_date="now").isoformat(),
            "updated_at": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
        }

        if custom_fields:
            base_deal.update(custom_fields)

        return base_deal

    def _generate_deal_name(self) -> str:
        """Generate realistic deal names."""
        company = fake.company()
        solution_types = [
            "Enterprise Software License",
            "Cloud Services Agreement",
            "Professional Services",
            "Support and Maintenance",
            "Training and Implementation",
            "Consulting Services",
            "Hardware Purchase",
            "Integration Services"
        ]
        solution = random.choice(solution_types)

        templates = [
            f"{company} - {solution}",
            f"{solution} for {company}",
            f"{company}: {solution} Project",
            f"Q{random.randint(1,4)}{fake.year()} {company} {solution}"
        ]

        return random.choice(templates)

    def generate_deal_batch(
        self,
        count: int,
        stage_distribution: Optional[Dict[str, float]] = None,
        amount_distribution: Optional[Dict[str, tuple]] = None
    ) -> List[Dict[str, Any]]:
        """Generate a batch of deals with realistic distribution."""
        deals = []

        # Default stage distribution based on typical sales funnel
        if stage_distribution is None:
            stage_distribution = {
                "prospecting": 0.15,
                "qualification": 0.20,
                "needs_analysis": 0.15,
                "proposal": 0.15,
                "negotiation": 0.10,
                "closed_won": 0.20,
                "closed_lost": 0.05
            }

        # Default amount distribution by customer size
        if amount_distribution is None:
            amount_distribution = {
                "small": (5000, 25000),
                "medium": (25000, 100000),
                "enterprise": (100000, 500000),
                "strategic": (500000, 2000000)
            }

        for i in range(count):
            # Select stage based on distribution
            stage = random.choices(
                list(stage_distribution.keys()),
                weights=list(stage_distribution.values())
            )[0]

            # Select amount range based on customer size
            customer_size = random.choices(
                list(amount_distribution.keys()),
                weights=[0.6, 0.25, 0.12, 0.03]  # More small/medium customers
            )[0]

            amount_range = amount_distribution[customer_size]

            deal = self.generate_deal(
                deal_id=f"batch_deal_{i:04d}",
                stage=stage,
                amount_range=amount_range,
                custom_fields={"customer_size": customer_size}
            )
            deals.append(deal)

        return deals

    def generate_edge_case_deals(self) -> List[Dict[str, Any]]:
        """Generate edge case deals for testing."""
        edge_cases = []

        # Minimum amount deal
        edge_cases.append(self.generate_deal(
            deal_id="edge_min_amount",
            amount_range=(1, 1),
            custom_fields={"description": "Minimum amount edge case"}
        ))

        # Maximum discount deal
        edge_cases.append(self.generate_deal(
            deal_id="edge_max_discount",
            discount_range=(95, 95),
            custom_fields={"description": "Maximum discount edge case"}
        ))

        # Very long payment terms
        edge_cases.append(self.generate_deal(
            deal_id="edge_long_terms",
            custom_fields={"payment_terms_days": 365}
        ))

        # Zero probability deal
        edge_cases.append(self.generate_deal(
            deal_id="edge_zero_prob",
            custom_fields={"probability": 0}
        ))

        # Special characters in name
        edge_cases.append(self.generate_deal(
            deal_id="edge_special_chars",
            custom_fields={
                "name": "Company & Co. LLC - Special Ñ Characters Deal",
                "description": "Deal with special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"
            }
        ))

        # Very old deal
        edge_cases.append(self.generate_deal(
            deal_id="edge_very_old",
            custom_fields={
                "created_at": (datetime.utcnow() - timedelta(days=1000)).isoformat()
            }
        ))

        # Future close date
        edge_cases.append(self.generate_deal(
            deal_id="edge_future_close",
            custom_fields={
                "expected_close": (datetime.utcnow() + timedelta(days=500)).isoformat()
            }
        ))

        return edge_cases


class PaymentDataGenerator:
    """Generator for payment test data."""

    def generate_payment(
        self,
        deal_id: str,
        amount: Optional[Decimal] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a single payment record."""
        if amount is None:
            amount = Decimal(str(random.uniform(1000, 100000)))

        if status is None:
            status_weights = [0.7, 0.15, 0.1, 0.05]  # succeeded, pending, failed, refunded
            status = random.choices(
                ["succeeded", "pending", "failed", "refunded"],
                weights=status_weights
            )[0]

        payment_methods = [
            "card_visa", "card_mastercard", "card_amex",
            "bank_transfer", "ach", "wire",
            "check", "purchase_order"
        ]

        payment = {
            "id": f"payment_{fake.uuid4()[:8]}",
            "deal_id": deal_id,
            "amount": str(amount),
            "currency": random.choice(["USD", "EUR", "GBP"]),
            "status": status,
            "payment_method": random.choice(payment_methods),
            "gateway_provider": random.choice(["stripe", "paypal", "adyen", "manual"]),
            "gateway_transaction_id": f"{random.choice(['ch_', 'pi_', 'pay_'])}{fake.uuid4()[:16]}",
            "failure_reason": None if status == "succeeded" else random.choice([
                "insufficient_funds", "card_declined", "invalid_cvv",
                "expired_card", "processing_error", "gateway_timeout"
            ]),
            "created_at": fake.date_time_between(start_date="-1y", end_date="now").isoformat(),
            "updated_at": fake.date_time_between(start_date="-30d", end_date="now").isoformat(),
        }

        if status == "refunded":
            payment["refunded_amount"] = str(amount * Decimal("0.8"))  # Partial refund
            payment["refund_reason"] = random.choice([
                "customer_request", "service_cancellation", "pricing_error"
            ])

        return payment

    def generate_idempotency_test_data(self) -> List[Dict[str, Any]]:
        """Generate data specifically for idempotency testing."""
        test_cases = []

        # Normal case
        test_cases.append({
            "description": "Normal payment processing",
            "idempotency_key": f"normal_{int(datetime.utcnow().timestamp())}",
            "deal_id": "deal_normal",
            "amount": "10000.00",
            "expected_result": "success"
        })

        # Duplicate request (same idempotency key)
        duplicate_key = f"duplicate_{int(datetime.utcnow().timestamp())}"
        test_cases.extend([
            {
                "description": "First request with duplicate key",
                "idempotency_key": duplicate_key,
                "deal_id": "deal_duplicate_1",
                "amount": "15000.00",
                "expected_result": "success"
            },
            {
                "description": "Second request with same key",
                "idempotency_key": duplicate_key,
                "deal_id": "deal_duplicate_2",
                "amount": "20000.00",
                "expected_result": "duplicate"
            }
        ])

        # Concurrent requests with same key
        concurrent_key = f"concurrent_{int(datetime.utcnow().timestamp())}"
        for i in range(5):
            test_cases.append({
                "description": f"Concurrent request {i+1}",
                "idempotency_key": concurrent_key,
                "deal_id": f"deal_concurrent_{i+1}",
                "amount": f"{10000 + (i * 1000)}.00",
                "expected_result": "concurrent_handled"
            })

        return test_cases


class SLADataGenerator:
    """Generator for SLA and KPI test data."""

    def generate_touch_rate_data(self, days: int = 7) -> Dict[str, Any]:
        """Generate realistic touch rate data for testing."""
        data = {"deals": [], "touch_times": []}

        for day in range(days):
            date = datetime.utcnow() - timedelta(days=day)

            # Generate 20-50 deals per day
            daily_deals = random.randint(20, 50)

            for i in range(daily_deals):
                created_at = date + timedelta(hours=random.randint(0, 23))

                # 95% touch rate: most deals touched within 5 minutes
                if random.random() < 0.95:
                    # Touched within 5 minutes
                    first_touch = created_at + timedelta(minutes=random.uniform(0.5, 4.5))
                else:
                    # Not touched within SLA window
                    first_touch = created_at + timedelta(minutes=random.uniform(10, 120))

                deal = {
                    "id": f"sla_deal_{day}_{i}",
                    "created_at": created_at.isoformat(),
                    "first_touch_at": first_touch.isoformat(),
                    "touched_within_sla": (first_touch - created_at).total_seconds() <= 300
                }

                data["deals"].append(deal)
                data["touch_times"].append((first_touch - created_at).total_seconds())

        return data

    def generate_qtc_time_data(self, months: int = 3) -> Dict[str, Any]:
        """Generate realistic quote-to-cash time data."""
        data = {"deals": []}

        for month in range(months):
            for week in range(4):
                # 5-15 deals per week
                weekly_deals = random.randint(5, 15)

                for i in range(weekly_deals):
                    created = datetime.utcnow() - timedelta(
                        days=month*30 + week*7 + random.randint(0, 6)
                    )

                    # Realistic QTC time distribution
                    # Most deals: 7-21 days
                    # Some outliers: 30-90 days
                    if random.random() < 0.8:
                        qtc_days = random.randint(7, 21)
                    else:
                        qtc_days = random.randint(30, 90)

                    closed = created + timedelta(days=qtc_days)

                    # Amount affects QTC time (larger deals take longer)
                    base_amount = random.uniform(5000, 50000)
                    if base_amount > 100000:
                        qtc_days += random.randint(5, 15)

                    deal = {
                        "id": f"qtc_deal_{month}_{week}_{i}",
                        "created_at": created.isoformat(),
                        "closed_at": closed.isoformat(),
                        "qtc_days": qtc_days,
                        "amount": base_amount,
                        "customer_size": random.choices(
                            ["small", "medium", "enterprise", "strategic"],
                            weights=[0.6, 0.25, 0.12, 0.03]
                        )[0]
                    }

                    data["deals"].append(deal)

        return data

    def generate_sla_breach_scenarios(self) -> List[Dict[str, Any]]:
        """Generate specific SLA breach scenarios for testing."""
        scenarios = []

        # Touch rate breach
        scenarios.append({
            "scenario": "touch_rate_breach",
            "description": "Touch rate falls below 95% threshold",
            "target_rate": 0.95,
            "actual_rate": 0.87,
            "affected_deals": 25,
            "time_period": "24_hours",
            "impact_level": "high"
        })

        # QTC time breach
        scenarios.append({
            "scenario": "qtc_time_breach",
            "description": "Average QTC time exceeds 15-day target",
            "target_days": 15,
            "actual_days": 22.5,
            "affected_deals": 40,
            "time_period": "30_days",
            "impact_level": "medium"
        })

        # Idempotency error rate breach
        scenarios.append({
            "scenario": "idempotency_error_breach",
            "description": "Idempotency error rate exceeds 0.5%",
            "target_rate": 0.005,
            "actual_rate": 0.012,
            "total_payments": 5000,
            "error_count": 60,
            "impact_level": "high"
        })

        return scenarios


class PolicyTestDataGenerator:
    """Generator for policy test data."""

    def generate_policy_configurations(self) -> Dict[str, Dict[str, Any]]:
        """Generate various policy configurations for testing."""
        configs = {}

        # Standard pricing policy
        configs["standard_pricing"] = {
            "discount_guardrails": {
                "default_max_discount_percent": 25,
                "risk_overrides": {"low": 30, "medium": 20, "high": 10},
                "requires_executive_approval_above": 20,
                "auto_approval_threshold": 5,
            },
            "payment_terms_guardrails": {
                "max_terms_days": 45,
                "requires_finance_review_above_days": 30,
                "standard_terms_options": [15, 30, 45],
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": 5000,
                "exceptions": ["pilot_programs", "strategic_accounts"],
            },
        }

        # Aggressive pricing policy
        configs["aggressive_pricing"] = {
            "discount_guardrails": {
                "default_max_discount_percent": 40,
                "risk_overrides": {"low": 50, "medium": 35, "high": 20},
                "requires_executive_approval_above": 30,
                "auto_approval_threshold": 10,
            },
            "payment_terms_guardrails": {
                "max_terms_days": 90,
                "requires_finance_review_above_days": 60,
                "standard_terms_options": [30, 60, 90],
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": 1000,
                "exceptions": ["all_channels"],
            },
        }

        # Conservative pricing policy
        configs["conservative_pricing"] = {
            "discount_guardrails": {
                "default_max_discount_percent": 15,
                "risk_overrides": {"low": 20, "medium": 10, "high": 5},
                "requires_executive_approval_above": 10,
                "auto_approval_threshold": 2,
            },
            "payment_terms_guardrails": {
                "max_terms_days": 30,
                "requires_finance_review_above_days": 15,
                "standard_terms_options": [15, 30],
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": 10000,
                "exceptions": [],
            },
        }

        # SLA policy
        configs["sla_policy"] = {
            "touch_rate_targets": {
                "five_minute_target": 0.95,
                "one_hour_target": 0.99,
                "twenty_four_hour_target": 1.0,
            },
            "response_time_thresholds": {
                "critical_alerts_minutes": 5,
                "high_priority_minutes": 15,
                "medium_priority_minutes": 60,
                "low_priority_hours": 4,
            },
            "escalation_rules": {
                "level1_after_minutes": 30,
                "level2_after_hours": 2,
                "level3_after_hours": 24,
                "executive_escalation_hours": 48,
            },
        }

        return configs

    def generate_policy_conflict_scenarios(self) -> List[Dict[str, Any]]:
        """Generate scenarios that create policy conflicts."""
        scenarios = []

        # Priority conflict
        scenarios.append({
            "scenario": "priority_conflict",
            "description": "Two policies with same priority but different rules",
            "policy1": {
                "id": "policy_1",
                "priority": 10,
                "config": {"max_discount": 25}
            },
            "policy2": {
                "id": "policy_2",
                "priority": 10,
                "config": {"max_discount": 35}
            },
            "expected_conflicts": ["priority", "configuration"]
        })

        # Configuration conflict
        scenarios.append({
            "scenario": "configuration_conflict",
            "description": "Policies with conflicting configuration values",
            "policy1": {
                "id": "policy_3",
                "priority": 5,
                "config": {"payment_terms": 30}
            },
            "policy2": {
                "id": "policy_4",
                "priority": 8,
                "config": {"payment_terms": 60}
            },
            "expected_conflicts": ["configuration"]
        })

        return scenarios

    def generate_impact_analysis_test_data(self) -> List[Dict[str, Any]]:
        """Generate test data for policy impact analysis."""
        test_deals = []

        # Small deals (unlikely to be affected)
        for i in range(20):
            test_deals.append({
                "id": f"impact_small_{i}",
                "amount": random.uniform(5000, 15000),
                "discount_percent": random.uniform(5, 15),
                "risk": random.choice(["low", "medium"]),
                "payment_terms_days": 30,
            })

        # Medium deals (some may be affected)
        for i in range(15):
            test_deals.append({
                "id": f"impact_medium_{i}",
                "amount": random.uniform(25000, 75000),
                "discount_percent": random.uniform(10, 25),
                "risk": random.choice(["medium", "high"]),
                "payment_terms_days": random.choice([30, 45, 60]),
            })

        # Large deals (likely to be affected)
        for i in range(10):
            test_deals.append({
                "id": f"impact_large_{i}",
                "amount": random.uniform(100000, 500000),
                "discount_percent": random.uniform(20, 35),
                "risk": "high",
                "payment_terms_days": random.choice([60, 90]),
            })

        # Problem deals (will definitely be affected)
        for i in range(5):
            test_deals.append({
                "id": f"impact_problem_{i}",
                "amount": random.uniform(50000, 200000),
                "discount_percent": random.uniform(40, 50),  # Very high discount
                "risk": "high",
                "payment_terms_days": 120,  # Very long terms
            })

        return test_deals


class PerformanceTestDataGenerator:
    """Generator for performance and load testing data."""

    def generate_load_test_scenarios(self) -> Dict[str, Any]:
        """Generate load test scenarios with different characteristics."""
        scenarios = {
            "light_load": {
                "concurrent_users": 10,
                "duration_seconds": 60,
                "ramp_up_seconds": 10,
                "requests_per_second": 5,
                "description": "Light load for baseline performance"
            },
            "moderate_load": {
                "concurrent_users": 50,
                "duration_seconds": 300,
                "ramp_up_seconds": 30,
                "requests_per_second": 20,
                "description": "Moderate load for typical usage"
            },
            "heavy_load": {
                "concurrent_users": 200,
                "duration_seconds": 600,
                "ramp_up_seconds": 60,
                "requests_per_second": 50,
                "description": "Heavy load for peak usage testing"
            },
            "stress_test": {
                "concurrent_users": 500,
                "duration_seconds": 900,
                "ramp_up_seconds": 120,
                "requests_per_second": 100,
                "description": "Stress test for system limits"
            }
        }
        return scenarios

    def generate_concurrent_deal_creation_data(self, count: int) -> List[Dict[str, Any]]:
        """Generate data for concurrent deal creation testing."""
        generator = DealDataGenerator()

        # Generate deals with varied characteristics to test different code paths
        deals = []
        for i in range(count):
            # Vary deal characteristics
            amount_multiplier = 1 + (i % 10)  # Vary amounts
            discount_modifier = (i % 25) * 0.5  # Vary discounts

            deal = generator.generate_deal(
                deal_id=f"concurrent_deal_{i:04d}",
                amount_range=(5000 * amount_multiplier, 25000 * amount_multiplier),
                discount_range=(discount_modifier, discount_modifier + 5)
            )
            deals.append(deal)

        return deals

    def generate_database_performance_queries(self) -> List[str]:
        """Generate SQL queries for database performance testing."""
        queries = [
            # Simple queries
            "SELECT COUNT(*) FROM deals",
            "SELECT * FROM deals ORDER BY created_at DESC LIMIT 10",

            # Complex queries with joins
            """
            SELECT d.name, d.amount, COUNT(p.id) as payment_count
            FROM deals d
            LEFT JOIN payments p ON d.id = p.deal_id
            WHERE d.created_at >= NOW() - INTERVAL '7 days'
            GROUP BY d.id, d.name, d.amount
            ORDER BY d.amount DESC
            """,

            # Aggregation queries
            """
            SELECT
                risk,
                stage,
                COUNT(*) as deal_count,
                AVG(amount) as avg_amount,
                SUM(amount) as total_amount
            FROM deals
            WHERE probability >= 50
            GROUP BY risk, stage
            HAVING COUNT(*) >= 2
            """,

            # Subqueries
            """
            SELECT * FROM deals
            WHERE amount > (
                SELECT AVG(amount) FROM deals
                WHERE created_at >= NOW() - INTERVAL '30 days'
            )
            """,

            # Window functions
            """
            SELECT
                name,
                amount,
                RANK() OVER (ORDER BY amount DESC) as amount_rank,
                LAG(amount) OVER (ORDER BY created_at) as prev_amount
            FROM deals
            WHERE stage = 'closed_won'
            """
        ]

        return queries


class ComplianceTestDataGenerator:
    """Generator for compliance and audit test data."""

    def generate_gdpr_test_data(self) -> Dict[str, Any]:
        """Generate test data for GDPR compliance testing."""
        return {
            "user_profiles": [
                {
                    "user_id": f"user_{i}",
                    "email": fake.email(),
                    "name": fake.name(),
                    "phone": fake.phone_number(),
                    "address": fake.address().replace('\n', ', '),
                    "ip_address": fake.ipv4(),
                    "consents": {
                        "marketing": random.choice([True, False]),
                        "analytics": True,
                        "third_party_sharing": random.choice([True, False]),
                        "consent_date": fake.date_time_between(start_date="-1y", end_date="now").isoformat()
                    },
                    "data_retention_days": random.randint(365, 2555),  # 1-7 years
                }
                for i in range(50)
            ],
            "data_requests": [
                {
                    "request_id": f"request_{i}",
                    "user_id": f"user_{i % 10}",
                    "request_type": random.choice(["export", "deletion", "correction"]),
                    "status": random.choice(["pending", "completed", "rejected"]),
                    "requested_at": fake.date_time_between(start_date="-30d", end_date="now").isoformat(),
                    "processed_at": fake.date_time_between(start_date="-15d", end_date="now").isoformat(),
                }
                for i in range(20)
            ]
        }

    def generate_security_test_scenarios(self) -> List[Dict[str, Any]]:
        """Generate security test scenarios."""
        scenarios = []

        # SQL injection attempts
        sql_injection_payloads = [
            "'; DROP TABLE deals; --",
            "1' OR '1'='1",
            "1' UNION SELECT * FROM users --",
            "'; UPDATE deals SET amount = 999999; --",
        ]

        for payload in sql_injection_payloads:
            scenarios.append({
                "test_type": "sql_injection",
                "payload": payload,
                "endpoint": "/deals",
                "method": "GET",
                "parameter": "search",
                "expected_status": [400, 422]  # Should reject malicious input
            })

        # XSS attempts
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "{{7*7}}",  # Template injection
        ]

        for payload in xss_payloads:
            scenarios.append({
                "test_type": "xss",
                "payload": payload,
                "endpoint": "/deals",
                "method": "POST",
                "parameter": "description",
                "expected_status": [400, 422]
            })

        # Authentication bypass attempts
        auth_scenarios = [
            {
                "test_type": "auth_bypass",
                "payload": "",
                "endpoint": "/deals",
                "method": "GET",
                "headers": {"Authorization": "Bearer invalid_token"},
                "expected_status": 401
            },
            {
                "test_type": "privilege_escalation",
                "payload": "",
                "endpoint": "/policies",
                "method": "GET",
                "headers": {"Authorization": "Bearer user_token"},  # User token for admin endpoint
                "expected_status": 403
            }
        ]

        scenarios.extend(auth_scenarios)

        return scenarios


# Factory functions for easy access
def create_deal_generator(seed: Optional[int] = None) -> DealDataGenerator:
    """Create a DealDataGenerator instance."""
    return DealDataGenerator(seed=seed)


def create_payment_generator() -> PaymentDataGenerator:
    """Create a PaymentDataGenerator instance."""
    return PaymentDataGenerator()


def create_sla_generator() -> SLADataGenerator:
    """Create an SLADataGenerator instance."""
    return SLADataGenerator()


def create_policy_generator() -> PolicyTestDataGenerator:
    """Create a PolicyTestDataGenerator instance."""
    return PolicyTestDataGenerator()


def create_performance_generator() -> PerformanceTestDataGenerator:
    """Create a PerformanceTestDataGenerator instance."""
    return PerformanceTestDataGenerator()


def create_compliance_generator() -> ComplianceTestDataGenerator:
    """Create a ComplianceTestDataGenerator instance."""
    return ComplianceTestDataGenerator()


# Convenience functions for common test data needs
def generate_test_deal_batch(count: int = 100) -> List[Dict[str, Any]]:
    """Generate a batch of test deals."""
    generator = DealDataGenerator()
    return generator.generate_deal_batch(count)


def generate_load_test_scenarios() -> Dict[str, Any]:
    """Get load test scenarios."""
    generator = PerformanceTestDataGenerator()
    return generator.generate_load_test_scenarios()


def generate_sla_breach_scenarios() -> List[Dict[str, Any]]:
    """Get SLA breach test scenarios."""
    generator = SLADataGenerator()
    return generator.generate_sla_breach_scenarios()