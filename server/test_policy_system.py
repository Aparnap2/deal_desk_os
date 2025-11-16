"""
Comprehensive tests for the Policy Management System
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
from app.models.policy import (
    Policy,
    PolicyStatus,
    PolicyType,
    PolicyTemplate,
    PolicyValidation,
)
from app.models.user import User, UserRole
from app.services.policy_service import PolicyService
from app.services.guardrail_service import evaluate_pricing_guardrails, initialize_policy_service


class TestPolicyService:
    """Test cases for PolicyService"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def policy_service(self, db_session):
        """Create policy service with mock session"""
        return PolicyService(db_session)

    @pytest.fixture
    def test_user(self):
        """Create test user"""
        return User(
            id="test-user-id",
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed_password",
            roles=[UserRole.REVOPS_ADMIN],
            is_active=True,
        )

    def test_create_policy_success(self, policy_service, db_session, test_user):
        """Test successful policy creation"""
        policy_name = "Test Policy"
        policy_type = PolicyType.PRICING
        configuration = {
            "discount_guardrails": {
                "default_max_discount_percent": 25,
                "risk_overrides": {"low": 30, "medium": 20, "high": 10},
                "requires_executive_approval_above": 20,
            },
            "payment_terms_guardrails": {
                "max_terms_days": 45,
                "requires_finance_review_above_days": 30,
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": 5000,
            },
        }

        # Mock database operations
        mock_policy = Policy(
            id="policy-123",
            name=policy_name,
            policy_type=policy_type,
            configuration=configuration,
            created_by_id=test_user.id,
            status=PolicyStatus.DRAFT,
        )
        db_session.add.return_value = None
        db_session.flush.return_value = None
        db_session.commit.return_value = None

        with patch.object(policy_service, '_log_policy_change') as mock_log, \
             patch.object(policy_service, '_validate_policy') as mock_validate:

            result = policy_service.create_policy(
                name=policy_name,
                policy_type=policy_type,
                configuration=configuration,
                created_by=test_user,
            )

            assert result.name == policy_name
            assert result.policy_type == policy_type
            assert result.configuration == configuration
            assert result.created_by_id == test_user.id
            assert result.status == PolicyStatus.DRAFT

            mock_log.assert_called_once()
            mock_validate.assert_called_once()

    def test_validate_pricing_policy_success(self, policy_service):
        """Test valid pricing policy configuration"""
        configuration = {
            "discount_guardrails": {
                "default_max_discount_percent": 25,
                "risk_overrides": {"low": 30, "medium": 20, "high": 10},
                "requires_executive_approval_above": 20,
            },
            "payment_terms_guardrails": {
                "max_terms_days": 45,
                "requires_finance_review_above_days": 30,
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": 5000,
            },
        }

        errors = policy_service.validate_policy_configuration(PolicyType.PRICING, configuration)
        assert len(errors) == 0

    def test_validate_pricing_policy_errors(self, policy_service):
        """Test invalid pricing policy configuration"""
        configuration = {
            "discount_guardrails": {
                "default_max_discount_percent": 150,  # Invalid: > 100
                "risk_overrides": {"low": 30, "medium": 20, "high": 10},
                "requires_executive_approval_above": 20,
            },
            "payment_terms_guardrails": {
                "max_terms_days": -10,  # Invalid: negative
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": -1000,  # Invalid: negative
            },
        }

        errors = policy_service.validate_policy_configuration(PolicyType.PRICING, configuration)
        assert len(errors) > 0
        assert any("must be between 0 and 100" in error for error in errors)
        assert any("must be positive" in error for error in errors)

    def test_validate_sla_policy(self, policy_service):
        """Test SLA policy validation"""
        # Valid SLA configuration
        valid_config = {
            "touch_rate_target": 0.95,
            "response_time_threshold": 24,
            "escalation_rules": {"level1_after": 48, "level2_after": 72},
        }

        errors = policy_service.validate_policy_configuration(PolicyType.SLA, valid_config)
        assert len(errors) == 0

        # Invalid SLA configuration
        invalid_config = {
            "touch_rate_target": 1.5,  # Invalid: > 1
            "response_time_threshold": -5,  # Invalid: negative
        }

        errors = policy_service.validate_policy_configuration(PolicyType.SLA, invalid_config)
        assert len(errors) > 0
        assert any("must be between 0 and 1" in error for error in errors)

    def test_evaluate_pricing_policy_for_deal(self, policy_service):
        """Test policy evaluation for deals"""
        policy = Policy(
            id="policy-123",
            name="Test Pricing Policy",
            policy_type=PolicyType.PRICING,
            configuration={
                "discount_guardrails": {
                    "default_max_discount_percent": 25,
                    "risk_overrides": {"low": 30, "medium": 20, "high": 10},
                    "requires_executive_approval_above": 20,
                },
                "payment_terms_guardrails": {
                    "max_terms_days": 45,
                    "requires_finance_review_above_days": 30,
                },
                "price_floor": {
                    "currency": "USD",
                    "min_amount": 5000,
                },
            },
        )

        # Test deal that passes all guardrails
        deal = Deal(
            amount=Decimal("10000"),
            discount_percent=Decimal("15"),
            payment_terms_days=30,
            risk=DealRisk.MEDIUM,
            currency="USD",
        )

        violation = policy_service._evaluate_pricing_policy_for_deal(policy, deal)
        assert violation is None

        # Test deal that exceeds discount limit
        deal_violation = Deal(
            amount=Decimal("10000"),
            discount_percent=Decimal("35"),  # Exceeds limit for medium risk
            payment_terms_days=30,
            risk=DealRisk.MEDIUM,
            currency="USD",
        )

        violation = policy_service._evaluate_pricing_policy_for_deal(policy, deal_violation)
        assert violation is not None
        assert violation["type"] == "discount_limit"
        assert "exceeds limit" in violation["message"]

    def test_simulate_policy_impact(self, policy_service, test_user):
        """Test policy impact simulation"""
        policy_id = "policy-123"
        test_deals = [
            {
                "id": "deal-1",
                "name": "Test Deal 1",
                "amount": 10000,
                "discount_percent": 15,
                "payment_terms_days": 30,
                "risk": "low",
            },
            {
                "id": "deal-2",
                "name": "Test Deal 2",
                "amount": 15000,
                "discount_percent": 35,  # Will violate
                "payment_terms_days": 60,  # Will violate
                "risk": "medium",
            },
        ]

        mock_policy = Policy(
            id=policy_id,
            name="Test Policy",
            policy_type=PolicyType.PRICING,
            configuration={
                "discount_guardrails": {"default_max_discount_percent": 25},
                "payment_terms_guardrails": {"max_terms_days": 45},
                "price_floor": {"currency": "USD", "min_amount": 5000},
            },
        )

        with patch.object(policy_service, 'get_policy_by_id', return_value=mock_policy), \
             patch.object(policy_service, 'evaluate_policy_for_deal') as mock_evaluate:

            # Mock evaluation results
            mock_evaluate.side_effect = [
                {"passed": True, "violations": []},
                {"passed": False, "violations": [{"type": "discount_limit"}]},
            ]

            simulation = policy_service.simulate_policy_impact(policy_id, test_deals, test_user)

            assert simulation.policy_id == policy_id
            assert simulation.simulation_type == "impact_analysis"
            assert simulation.results["summary"]["total_deals"] == 2
            assert simulation.results["summary"]["passed_deals"] == 1
            assert simulation.results["summary"]["failed_deals"] == 1
            assert simulation.results["summary"]["pass_rate"] == 0.5


class TestGuardrailService:
    """Test cases for updated GuardrailService"""

    def test_load_pricing_policy_from_db(self):
        """Test loading pricing policy from database"""
        # Mock database session and service
        mock_db = Mock(spec=Session)
        mock_policy = Policy(
            id="policy-123",
            name="Test Policy",
            policy_type=PolicyType.PRICING,
            configuration={
                "discount_guardrails": {"default_max_discount_percent": 25},
                "payment_terms_guardrails": {"max_terms_days": 45},
                "price_floor": {"currency": "USD", "min_amount": 5000},
            },
            priority=10,
        )

        mock_service = Mock()
        mock_service.get_policies.return_value = [mock_policy]

        # Initialize policy service
        with patch('app.services.guardrail_service.PolicyService', return_value=mock_service):
            initialize_policy_service(mock_db)

            # Load policy
            from app.services.guardrail_service import load_pricing_policy
            policy = load_pricing_policy()

            assert policy["discount_guardrails"]["default_max_discount_percent"] == 25
            assert policy["payment_terms_guardrails"]["max_terms_days"] == 45
            assert policy["price_floor"]["min_amount"] == 5000

    def test_evaluate_pricing_guardrails_integration(self):
        """Test integration of policy evaluation with guardrails"""
        # This tests that the guardrail service can still work with the new policy system
        from app.services.guardrail_service import initialize_policy_service

        # Mock the policy service to return our test policy
        mock_policy = {
            "discount_guardrails": {"default_max_discount_percent": 25, "risk_overrides": {"low": 30, "medium": 20, "high": 10}},
            "payment_terms_guardrails": {"max_terms_days": 45, "requires_finance_review_above_days": 30},
            "price_floor": {"currency": "USD", "min_amount": 5000},
        }

        with patch('app.services.guardrail_service.load_pricing_policy', return_value=mock_policy):
            evaluation = evaluate_pricing_guardrails(
                amount=Decimal("10000"),
                discount_percent=15.0,
                payment_terms_days=30,
                risk=DealRisk.MEDIUM,
            )

            assert evaluation.status == GuardrailStatus.PASS
            assert evaluation.requires_manual_review is False

            # Test violation case
            evaluation_violation = evaluate_pricing_guardrails(
                amount=Decimal("10000"),
                discount_percent=35.0,  # Exceeds limit
                payment_terms_days=30,
                risk=DealRisk.MEDIUM,
            )

            assert evaluation_violation.status == GuardrailStatus.VIOLATED
            assert "exceeds" in evaluation_violation.reason.lower()


class TestPolicyConflicts:
    """Test cases for policy conflict detection"""

    @pytest.fixture
    def policy_service(self):
        """Create policy service with mock session"""
        db = Mock(spec=Session)
        return PolicyService(db)

    def test_detect_priority_conflicts(self, policy_service):
        """Test detection of priority conflicts"""
        policy1 = Policy(
            id="policy-1",
            name="Policy 1",
            policy_type=PolicyType.PRICING,
            priority=10,
        )
        policy2 = Policy(
            id="policy-2",
            name="Policy 2",
            policy_type=PolicyType.PRICING,
            priority=10,  # Same priority as policy1
        )

        conflicts = policy_service._detect_policy_conflicts(policy1, policy2)
        assert len(conflicts) > 0
        assert any(conflict["type"] == "priority" for conflict in conflicts)

    def test_detect_configuration_conflicts(self, policy_service):
        """Test detection of configuration conflicts"""
        policy1 = Policy(
            id="policy-1",
            name="Policy 1",
            policy_type=PolicyType.PRICING,
            configuration={
                "discount_guardrails": {"default_max_discount_percent": 25},
            },
            priority=10,
        )
        policy2 = Policy(
            id="policy-2",
            name="Policy 2",
            policy_type=PolicyType.PRICING,
            configuration={
                "discount_guardrails": {"default_max_discount_percent": 35},  # Different
            },
            priority=20,
        )

        conflicts = policy_service._detect_policy_conflicts(policy1, policy2)
        assert len(conflicts) > 0
        assert any(conflict["type"] == "configuration" for conflict in conflicts)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])