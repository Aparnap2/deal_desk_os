"""
Comprehensive Policy Editor functionality testing.

This module tests:
- Policy CRUD operations
- Policy validation and conflict detection
- Policy versioning and rollback
- Migration from JSON to database
- Impact analysis accuracy
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy, PolicyStatus, PolicyType, PolicyValidation, PolicyPriority
from app.models.user import User, UserRole
from app.services.policy_service import PolicyService
from app.services.guardrail_service import evaluate_pricing_guardrails


class TestPolicyCRUDOperations:
    """Testing Policy Create, Read, Update, Delete operations."""

    @pytest_asyncio.asyncio
    async def test_create_pricing_policy_success(self, async_db_session, test_admin_user):
        """Test successful creation of a pricing policy."""
        policy_service = PolicyService(async_db_session)

        policy_data = {
            "name": "Standard Pricing Policy",
            "description": "Default pricing guardrails for standard deals",
            "policy_type": PolicyType.PRICING,
            "configuration": {
                "discount_guardrails": {
                    "default_max_discount_percent": 25,
                    "risk_overrides": {
                        "low": 30,
                        "medium": 20,
                        "high": 10
                    },
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
            },
            "priority": PolicyPriority.HIGH,
        }

        policy = await policy_service.create_policy(
            name=policy_data["name"],
            policy_type=policy_data["policy_type"],
            configuration=policy_data["configuration"],
            description=policy_data["description"],
            created_by=test_admin_user,
            priority=policy_data["priority"],
        )

        assert policy.id is not None
        assert policy.name == policy_data["name"]
        assert policy.policy_type == PolicyType.PRICING
        assert policy.status == PolicyStatus.DRAFT
        assert policy.configuration == policy_data["configuration"]
        assert policy.created_by_id == test_admin_user.id

    @pytest_asyncio.asyncio
    async def test_create_sla_policy_success(self, async_db_session, test_admin_user):
        """Test successful creation of an SLA policy."""
        policy_service = PolicyService(async_db_session)

        sla_config = {
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

        policy = await policy_service.create_policy(
            name="Standard SLA Policy",
            policy_type=PolicyType.SLA,
            configuration=sla_config,
            description="Service Level Agreement targets and escalation rules",
            created_by=test_admin_user,
        )

        assert policy.policy_type == PolicyType.SLA
        assert policy.configuration["touch_rate_targets"]["five_minute_target"] == 0.95

    @pytest_asyncio.asyncio
    async def test_update_policy_configuration(self, async_db_session, test_policy, test_admin_user):
        """Test updating policy configuration."""
        policy_service = PolicyService(async_db_session)

        # Update configuration
        updated_config = test_policy.configuration.copy()
        updated_config["discount_guardrails"]["default_max_discount_percent"] = 30  # Increased from 25

        updated_policy = await policy_service.update_policy(
            policy_id=test_policy.id,
            configuration=updated_config,
            updated_by=test_admin_user,
            update_reason="Increase discount limits for competitive reasons"
        )

        assert updated_policy.configuration["discount_guardrails"]["default_max_discount_percent"] == 30
        assert updated_policy.updated_at > test_policy.updated_at

        # Verify version was created
        assert updated_policy.version > test_policy.version

    @pytest_asyncio.asyncio
    async def test_policy_deactivation(self, async_db_session, test_policy, test_admin_user):
        """Test deactivating a policy."""
        policy_service = PolicyService(async_db_session)

        await policy_service.deactivate_policy(
            policy_id=test_policy.id,
            deactivated_by=test_admin_user,
            reason="Replaced with new policy guidelines"
        )

        deactivated_policy = await policy_service.get_policy_by_id(test_policy.id)
        assert deactivated_policy.status == PolicyStatus.INACTIVE
        assert deactivated_policy.deactivated_at is not None

    @pytest_asyncio.asyncio
    async def test_list_policies_with_filters(self, async_db_session, generate_test_policy):
        """Test listing policies with various filters."""
        policy_service = PolicyService(async_db_session)

        # Create policies of different types and statuses
        policies = [
            generate_test_policy(PolicyType.PRICING, status=PolicyStatus.ACTIVE),
            generate_test_policy(PolicyType.SLA, status=PolicyStatus.DRAFT),
            generate_test_policy(PolicyType.PRICING, status=PolicyStatus.INACTIVE),
            generate_test_policy(PolicyType.SLA, status=PolicyStatus.ACTIVE),
        ]

        for policy in policies:
            async_db_session.add(policy)
        await async_db_session.commit()

        # Test filtering by type
        pricing_policies = await policy_service.list_policies(policy_type=PolicyType.PRICING)
        assert len(pricing_policies) == 2

        # Test filtering by status
        active_policies = await policy_service.list_policies(status=PolicyStatus.ACTIVE)
        assert len(active_policies) == 2

        # Test combined filters
        active_sla_policies = await policy_service.list_policies(
            policy_type=PolicyType.SLA,
            status=PolicyStatus.ACTIVE
        )
        assert len(active_sla_policies) == 1


class TestPolicyValidation:
    """Testing policy configuration validation."""

    @pytest_asyncio.asyncio
    async def test_validate_pricing_policy_configuration(self, async_db_session):
        """Test validation of pricing policy configurations."""
        policy_service = PolicyService(async_db_session)

        # Valid configuration
        valid_config = {
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

        errors = policy_service.validate_policy_configuration(PolicyType.PRICING, valid_config)
        assert len(errors) == 0

    @pytest_asyncio.asyncio
    async def test_validate_invalid_pricing_policy(self, async_db_session):
        """Test validation of invalid pricing policy configurations."""
        policy_service = PolicyService(async_db_session)

        # Invalid configuration with multiple issues
        invalid_config = {
            "discount_guardrails": {
                "default_max_discount_percent": 150,  # Invalid: > 100
                "risk_overrides": {"low": 30, "medium": -5, "high": 10},  # Invalid: negative
                "requires_executive_approval_above": 20,
                "auto_approval_threshold": 15,  # Invalid: > approval threshold
            },
            "payment_terms_guardrails": {
                "max_terms_days": -10,  # Invalid: negative
                "requires_finance_review_above_days": 365,  # Invalid: > 1 year
                "standard_terms_options": [15, "30", 45],  # Invalid: mixed types
            },
            "price_floor": {
                "currency": "USD",
                "min_amount": -1000,  # Invalid: negative
                "exceptions": "not_a_list",  # Invalid: should be list
            },
        }

        errors = policy_service.validate_policy_configuration(PolicyType.PRICING, invalid_config)
        assert len(errors) >= 6  # At least 6 validation errors

        # Check specific error messages
        error_messages = " ".join(errors)
        assert "must be between 0 and 100" in error_messages
        assert "must be positive" in error_messages
        assert "must be less than" in error_messages

    @pytest_asyncio.asyncio
    async def test_validate_sla_policy_configuration(self, async_db_session):
        """Test validation of SLA policy configurations."""
        policy_service = PolicyService(async_db_session)

        # Valid SLA configuration
        valid_sla_config = {
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

        errors = policy_service.validate_policy_configuration(PolicyType.SLA, valid_sla_config)
        assert len(errors) == 0

        # Invalid SLA configuration
        invalid_sla_config = {
            "touch_rate_targets": {
                "five_minute_target": 1.5,  # Invalid: > 1
                "one_hour_target": 0.99,
                "twenty_four_hour_target": 1.0,
            },
            "response_time_thresholds": {
                "critical_alerts_minutes": -5,  # Invalid: negative
                "high_priority_minutes": 15,
                "medium_priority_minutes": 60,
                "low_priority_hours": 4,
            },
        }

        errors = policy_service.validate_policy_configuration(PolicyType.SLA, invalid_sla_config)
        assert len(errors) >= 2

    @pytest_asyncio.asyncio
    async def test_policy_validation_with_custom_rules(self, async_db_session):
        """Test policy validation with custom validation rules."""
        policy_service = PolicyService(async_db_session)

        # Configuration that passes basic validation but fails custom rules
        custom_rule_config = {
            "discount_guardrails": {
                "default_max_discount_percent": 25,
                "risk_overrides": {"low": 35, "medium": 20, "high": 10},  # Low risk too high
                "requires_executive_approval_above": 20,
                "auto_approval_threshold": 5,
            },
            "custom_rules": {
                "max_discount_for_strategic_accounts": 40,
                "min_deal_size_for_custom_terms": 100000,
            },
        }

        errors = policy_service.validate_policy_configuration(
            PolicyType.PRICING,
            custom_rule_config,
            apply_custom_rules=True
        )

        # Should detect business logic violations
        assert len(errors) > 0


class TestPolicyConflictDetection:
    """Testing policy conflict detection and resolution."""

    @pytest_asyncio.asyncio
    async def test_detect_priority_conflicts(self, async_db_session, generate_test_policy):
        """Test detection of priority conflicts between policies."""
        policy_service = PolicyService(async_db_session)

        # Create two pricing policies with same priority
        policy1 = generate_test_policy(
            PolicyType.PRICING,
            priority=PolicyPriority.MEDIUM,
            configuration={"discount_guardrails": {"default_max_discount_percent": 25}}
        )

        policy2 = generate_test_policy(
            PolicyType.PRICING,
            priority=PolicyPriority.MEDIUM,  # Same priority as policy1
            configuration={"discount_guardrails": {"default_max_discount_percent": 30}}  # Different values
        )

        conflicts = policy_service._detect_policy_conflicts(policy1, policy2)

        assert len(conflicts) > 0
        assert any(conflict["type"] == "priority" for conflict in conflicts)
        assert any(conflict["type"] == "configuration" for conflict in conflicts)

    @pytest_asyncio.asyncio
    async def test_detect_configuration_conflicts(self, async_db_session, generate_test_policy):
        """Test detection of configuration conflicts between policies."""
        policy_service = PolicyService(async_db_session)

        # Create policies with conflicting configurations
        policy1 = generate_test_policy(
            PolicyType.PRICING,
            priority=PolicyPriority.HIGH,
            configuration={
                "discount_guardrails": {"default_max_discount_percent": 20},
                "payment_terms_guardrails": {"max_terms_days": 30}
            }
        )

        policy2 = generate_test_policy(
            PolicyType.PRICING,
            priority=PolicyPriority.LOWER,  # Lower priority
            configuration={
                "discount_guardrails": {"default_max_discount_percent": 40},  # Conflicts with policy1
                "payment_terms_guardrails": {"max_terms_days": 60}  # Conflicts with policy1
            }
        )

        conflicts = policy_service._detect_policy_conflicts(policy1, policy2)

        assert len(conflicts) > 0
        assert any(conflict["type"] == "configuration" for conflict in conflicts)

        configuration_conflicts = [c for c in conflicts if c["type"] == "configuration"]
        assert len(configuration_conflicts) >= 2  # Both discount and terms conflicts

    @pytest_asyncio.asyncio
    async def test_suggest_conflict_resolution(self, async_db_session, generate_test_policy):
        """Test conflict resolution suggestions."""
        policy_service = PolicyService(async_db_session)

        policy1 = generate_test_policy(
            PolicyType.PRICING,
            priority=PolicyPriority.HIGH,
            configuration={"discount_guardrails": {"default_max_discount_percent": 20}}
        )

        policy2 = generate_test_policy(
            PolicyType.PRICING,
            priority=PolicyPriority.HIGH,  # Same priority
            configuration={"discount_guardrails": {"default_max_discount_percent": 30}}
        )

        resolution_suggestions = policy_service.suggest_conflict_resolution(policy1, policy2)

        assert "priority_adjustment" in resolution_suggestions
        assert "configuration_merge" in resolution_suggestions
        assert "recommendation" in resolution_suggestions

        # Should recommend priority adjustment
        assert resolution_suggestions["priority_adjustment"]["action"] == "adjust_priority"

    @pytest_asyncio.asyncio
    async def test_check_policy_compatibility(self, async_db_session, generate_test_policy):
        """Test checking overall policy compatibility."""
        policy_service = PolicyService(async_db_session)

        # Create multiple policies
        policies = [
            generate_test_policy(PolicyType.PRICING, priority=PolicyPriority.HIGH),
            generate_test_policy(PolicyType.SLA, priority=PolicyPriority.MEDIUM),
            generate_test_policy(PolicyType.PRICING, priority=PolicyPriority.LOWER),
        ]

        compatibility_report = policy_service.check_policy_compatibility(policies)

        assert "conflicts" in compatibility_report
        assert "recommendations" in compatibility_report
        assert "compatible" in compatibility_report

        # Should have at least one conflict (two pricing policies)
        assert len(compatibility_report["conflicts"]) >= 1


class TestPolicyVersioning:
    """Testing policy versioning and rollback functionality."""

    @pytest_asyncio.asyncio
    async def test_policy_version_creation(self, async_db_session, test_policy, test_admin_user):
        """Test that policy updates create new versions."""
        policy_service = PolicyService(async_db_session)

        original_version = test_policy.version
        updated_config = test_policy.configuration.copy()
        updated_config["discount_guardrails"]["default_max_discount_percent"] = 35

        updated_policy = await policy_service.update_policy(
            policy_id=test_policy.id,
            configuration=updated_config,
            updated_by=test_admin_user,
            update_reason="Business requirement update"
        )

        assert updated_policy.version == original_version + 1
        assert updated_policy.configuration["discount_guardrails"]["default_max_discount_percent"] == 35

        # Verify version history is maintained
        version_history = await policy_service.get_policy_version_history(test_policy.id)
        assert len(version_history) == 2
        assert version_history[0].version == original_version
        assert version_history[1].version == updated_policy.version

    @pytest_asyncio.asyncio
    async def test_policy_rollback_to_previous_version(self, async_db_session, test_policy, test_admin_user):
        """Test rolling back a policy to a previous version."""
        policy_service = PolicyService(async_db_session)

        # Create multiple versions
        original_config = test_policy.configuration.copy()

        # Version 2
        updated_config_v2 = original_config.copy()
        updated_config_v2["discount_guardrails"]["default_max_discount_percent"] = 30
        await policy_service.update_policy(
            policy_id=test_policy.id,
            configuration=updated_config_v2,
            updated_by=test_admin_user,
            update_reason="Version 2 update"
        )

        # Version 3
        updated_config_v3 = original_config.copy()
        updated_config_v3["discount_guardrails"]["default_max_discount_percent"] = 40
        await policy_service.update_policy(
            policy_id=test_policy.id,
            configuration=updated_config_v3,
            updated_by=test_admin_user,
            update_reason="Version 3 update"
        )

        # Rollback to version 2
        rolled_back_policy = await policy_service.rollback_policy(
            policy_id=test_policy.id,
            target_version=2,
            rolled_back_by=test_admin_user,
            rollback_reason="Version 3 too aggressive"
        )

        assert rolled_back_policy.configuration["discount_guardrails"]["default_max_discount_percent"] == 30
        assert rolled_back_policy.version > 3  # New version created for rollback

    @pytest_asyncio.asyncio
    async def test_policy_diff_between_versions(self, async_db_session, test_policy, test_admin_user):
        """Test generating diffs between policy versions."""
        policy_service = PolicyService(async_db_session)

        # Create new version with different config
        updated_config = test_policy.configuration.copy()
        updated_config["discount_guardrails"]["default_max_discount_percent"] = 35
        updated_config["payment_terms_guardrails"]["max_terms_days"] = 60
        del updated_config["price_floor"]  # Remove section

        await policy_service.update_policy(
            policy_id=test_policy.id,
            configuration=updated_config,
            updated_by=test_admin_user,
            update_reason="Remove price floor, increase limits"
        )

        # Get diff between versions
        diff = await policy_service.get_policy_version_diff(
            policy_id=test_policy.id,
            from_version=1,
            to_version=2
        )

        assert "changes" in diff
        assert "summary" in diff

        changes = diff["changes"]
        assert len(changes) >= 3  # Should have at least 3 changes

        # Check specific changes
        discount_change = next((c for c in changes if c["path"] == "discount_guardrails.default_max_discount_percent"), None)
        assert discount_change is not None
        assert discount_change["old_value"] == 25
        assert discount_change["new_value"] == 35

        price_floor_removal = next((c for c in changes if c["path"] == "price_floor" and c["type"] == "removed"), None)
        assert price_floor_removal is not None


class TestPolicyMigrationFromJson:
    """Testing migration of policies from JSON files to database."""

    @pytest_asyncio.asyncio
    async def test_json_policy_import(self, async_db_session, test_admin_user):
        """Test importing policies from JSON configuration."""
        policy_service = PolicyService(async_db_session)

        # Sample JSON policy data
        json_policies = [
            {
                "name": "Legacy Pricing Policy",
                "description": "Imported from legacy JSON configuration",
                "policy_type": "pricing",
                "configuration": {
                    "discount_limits": {"standard": 20, "strategic": 35},
                    "payment_terms": {"standard": 30, "extended": 60},
                },
                "priority": 1,
                "enabled": True,
            },
            {
                "name": "Legacy SLA Policy",
                "description": "Legacy SLA configuration",
                "policy_type": "sla",
                "configuration": {
                    "response_times": {"urgent": 15, "normal": 60},
                    "escalation": {"level1": 30, "level2": 120},
                },
                "priority": 2,
                "enabled": True,
            }
        ]

        # Import policies
        import_results = await policy_service.import_policies_from_json(
            json_policies=json_policies,
            imported_by=test_admin_user,
            validate_before_import=True
        )

        assert "imported" in import_results
        assert "skipped" in import_results
        assert "errors" in import_results

        assert len(import_results["imported"]) == 2
        assert len(import_results["skipped"]) == 0
        assert len(import_results["errors"]) == 0

        # Verify policies were created
        imported_policy = import_results["imported"][0]
        assert imported_policy.name == "Legacy Pricing Policy"
        assert imported_policy.policy_type == PolicyType.PRICING

    @pytest_asyncio.asyncio
    async def test_json_policy_validation_during_import(self, async_db_session, test_admin_user):
        """Test validation during JSON policy import."""
        policy_service = PolicyService(async_db_session)

        # JSON with invalid policy
        invalid_json_policies = [
            {
                "name": "Invalid Pricing Policy",
                "policy_type": "pricing",
                "configuration": {
                    "discount_limits": {"standard": 150},  # Invalid discount > 100%
                },
            }
        ]

        import_results = await policy_service.import_policies_from_json(
            json_policies=invalid_json_policies,
            imported_by=test_admin_user,
            validate_before_import=True,
            skip_invalid=True  # Skip invalid policies but continue
        )

        assert len(import_results["imported"]) == 0
        assert len(import_results["skipped"]) == 1
        assert len(import_results["errors"]) == 1

    @pytest_asyncio.asyncio
    async def test_json_configuration_transformation(self, async_db_session, test_admin_user):
        """Test transformation of legacy JSON configuration to new schema."""
        policy_service = PolicyService(async_db_session)

        # Legacy format that needs transformation
        legacy_config = {
            "name": "Legacy Guardrails",
            "policy_type": "pricing",
            "rules": {
                "max_discount": 25,
                "min_deal_size": 10000,
                "payment_terms": {
                    "standard": "NET30",
                    "extended": "NET60",
                }
            },
            "conditions": {
                "risk_adjustments": {
                    "low": "+5%",
                    "high": "-10%",
                }
            }
        }

        # Transform and import
        transformed_policy = await policy_service.transform_legacy_policy(
            legacy_policy=legacy_config,
            target_version="2.0"
        )

        assert transformed_policy["configuration"]["discount_guardrails"]["default_max_discount_percent"] == 25
        assert transformed_policy["configuration"]["price_floor"]["min_amount"] == 10000
        assert "risk_overrides" in transformed_policy["configuration"]["discount_guardrails"]


class TestPolicyImpactAnalysis:
    """Testing policy impact analysis accuracy."""

    @pytest_asyncio.asyncio
    async def test_simulate_policy_impact_on_deals(self, async_db_session, test_policy, generate_test_deal):
        """Test simulating policy impact on existing deals."""
        policy_service = PolicyService(async_db_session)

        # Create test deals with different characteristics
        test_deals = [
            generate_test_deal(
                amount=Decimal("8000"),
                discount_percent=Decimal("15"),
                risk="low",
                payment_terms_days=30,
            ),
            generate_test_deal(
                amount=Decimal("50000"),
                discount_percent=Decimal("35"),  # Will violate new stricter policy
                risk="medium",
                payment_terms_days=60,  # Will violate new stricter terms
            ),
            generate_test_deal(
                amount=Decimal("15000"),
                discount_percent=Decimal("12"),
                risk="low",
                payment_terms_days=45,
            ),
        ]

        # Simulate impact with stricter policy
        stricter_config = {
            "discount_guardrails": {
                "default_max_discount_percent": 20,  # Reduced from 25
                "risk_overrides": {"low": 25, "medium": 15, "high": 5},
                "requires_executive_approval_above": 15,
            },
            "payment_terms_guardrails": {
                "max_terms_days": 30,  # Reduced from 45
                "requires_finance_review_above_days": 30,
            },
        }

        impact_analysis = await policy_service.simulate_policy_impact(
            policy_id=test_policy.id,
            deals=[deal.__dict__ for deal in test_deals],
            new_configuration=stricter_config,
            test_user=test_policy.created_by_id
        )

        assert "policy_id" in impact_analysis
        assert "summary" in impact_analysis
        assert "detailed_results" in impact_analysis

        summary = impact_analysis["summary"]
        assert summary["total_deals"] == 3
        assert summary["passed_deals"] == 2  # Two deals pass new policy
        assert summary["failed_deals"] == 1  # One deal fails new policy
        assert summary["pass_rate"] == 2/3

    @pytest_asyncio.asyncio
    async def test_financial_impact_analysis(self, async_db_session, test_policy):
        """Test financial impact analysis of policy changes."""
        policy_service = PolicyService(async_db_session)

        # Create deals with financial data
        deals_with_financials = [
            {
                "id": "deal_1",
                "amount": 20000,
                "discount_percent": 30,  # High discount
                "margin_percent": 15,
                "probability": 80,
            },
            {
                "id": "deal_2",
                "amount": 50000,
                "discount_percent": 35,  # Very high discount
                "margin_percent": 10,
                "probability": 90,
            },
        ]

        # New policy that reduces discounts
        new_policy_config = {
            "discount_guardrails": {
                "default_max_discount_percent": 20,  # Significant reduction
                "risk_overrides": {"low": 25, "medium": 15, "high": 10},
                "requires_executive_approval_above": 15,
            }
        }

        financial_impact = await policy_service.analyze_financial_impact(
            deals=deals_with_financials,
            current_policy_config=test_policy.configuration,
            new_policy_config=new_policy_config,
        )

        assert "revenue_impact" in financial_impact
        assert "margin_impact" in financial_impact
        assert "deal_velocity_impact" in financial_impact

        # Stricter policy should increase revenue (lower discounts)
        assert financial_impact["revenue_impact"]["total_increase"] > 0
        assert financial_impact["margin_impact"]["average_increase"] > 0

    @pytest_asyncio.asyncio
    async def test_operational_impact_analysis(self, async_db_session, test_policy):
        """Test operational impact analysis of policy changes."""
        policy_service = PolicyService(async_db_session)

        # Deals with operational characteristics
        deals_with_ops_data = [
            {
                "id": "deal_ops_1",
                "requires_approval": False,  # Currently auto-approved
                "approval_time_minutes": 0,
                "touches_required": 2,
            },
            {
                "id": "deal_ops_2",
                "requires_approval": True,  # Currently requires approval
                "approval_time_minutes": 45,
                "touches_required": 5,
            },
        ]

        # New policy that requires more approvals
        new_policy_config = {
            "discount_guardrails": {
                "default_max_discount_percent": 15,  # Very restrictive
                "auto_approval_threshold": 2,  # Only very small discounts auto-approved
                "requires_executive_approval_above": 10,  # Lower threshold
            }
        }

        operational_impact = await policy_service.analyze_operational_impact(
            deals=deals_with_ops_data,
            current_policy_config=test_policy.configuration,
            new_policy_config=new_policy_config,
        )

        assert "approval_workload" in operational_impact
        assert "processing_time" in operational_impact
        assert "escalation_volume" in operational_impact

        # More restrictive policy should increase workload
        assert operational_impact["approval_workload"]["additional_approvals_required"] > 0
        assert operational_impact["processing_time"]["average_increase_minutes"] > 0

    @pytest_asyncio.asyncio
    async def test_risk_assessment_of_policy_changes(self, async_db_session, test_policy):
        """Test risk assessment for proposed policy changes."""
        policy_service = PolicyService(async_db_session)

        # Simulate risk factors
        risk_factors = {
            "market_competitiveness": 0.8,  # High competition
            "sales_team_experience": 0.6,  # Medium experience
            "customer_price_sensitivity": 0.9,  # High sensitivity
            "historical_approval_rates": 0.7,  # Good historical rates
        }

        # Assess risk of making policy more restrictive
        risk_assessment = await policy_service.assess_policy_change_risk(
            current_policy=test_policy,
            proposed_changes={
                "discount_guardrails.default_max_discount_percent": 15,  # Major reduction
                "payment_terms_guardrails.max_terms_days": 30,  # Reduction
            },
            risk_factors=risk_factors
        )

        assert "overall_risk_level" in risk_assessment
        assert "risk_factors" in risk_assessment
        assert "recommendations" in risk_assessment
        assert "mitigation_strategies" in risk_assessment

        # Should identify high risk due to market factors
        assert risk_assessment["overall_risk_level"] in ["medium", "high"]
        assert len(risk_assessment["mitigation_strategies"]) > 0