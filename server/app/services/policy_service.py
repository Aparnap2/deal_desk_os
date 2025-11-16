from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, with_polymorphic

from app.models.deal import Deal, DealRisk, GuardrailStatus
from app.models.policy import (
    Policy,
    PolicyConflict,
    PolicyChangeLog,
    PolicyChangeType,
    PolicySimulation,
    PolicyStatus,
    PolicyTemplate,
    PolicyType,
    PolicyValidation,
    PolicyVersion,
)
from app.models.user import User

POLICY_PATH = Path(__file__).resolve().parents[3] / "shared" / "policies" / "pricing_policy_v1.json"


class PolicyService:
    def __init__(self, db: Session):
        self.db = db

    # Policy Template Management
    def get_templates(self, policy_type: Optional[str] = None) -> List[PolicyTemplate]:
        """Get policy templates, optionally filtered by type"""
        query = select(PolicyTemplate).where(PolicyTemplate.is_system_template == False)
        if policy_type:
            query = query.where(PolicyTemplate.policy_type == policy_type)
        return list(self.db.execute(query).scalars().all())

    def get_template_by_id(self, template_id: str) -> Optional[PolicyTemplate]:
        """Get a specific policy template"""
        return self.db.get(PolicyTemplate, template_id)

    # Policy CRUD Operations
    def get_policies(
        self,
        policy_type: Optional[PolicyType] = None,
        status: Optional[PolicyStatus] = None,
        include_inactive: bool = False,
    ) -> List[Policy]:
        """Get policies with optional filtering"""
        query = select(Policy)

        if policy_type:
            query = query.where(Policy.policy_type == policy_type)

        if status:
            query = query.where(Policy.status == status)
        elif not include_inactive:
            query = query.where(Policy.status == PolicyStatus.ACTIVE)

        query = query.order_by(Policy.priority.desc(), Policy.created_at.desc())
        return list(self.db.execute(query).scalars().all())

    def get_policy_by_id(self, policy_id: str) -> Optional[Policy]:
        """Get a specific policy"""
        return self.db.get(Policy, policy_id)

    def create_policy(
        self,
        name: str,
        policy_type: PolicyType,
        configuration: Dict[str, Any],
        created_by: User,
        description: Optional[str] = None,
        template_id: Optional[str] = None,
        effective_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        priority: int = 0,
        tags: Optional[List[str]] = None,
    ) -> Policy:
        """Create a new policy"""
        policy = Policy(
            name=name,
            description=description,
            policy_type=policy_type,
            configuration=configuration,
            created_by_id=created_by.id,
            template_id=template_id,
            effective_at=effective_at,
            expires_at=expires_at,
            priority=priority,
            tags=tags or [],
            status=PolicyStatus.DRAFT,
            version="1.0.0",
        )

        self.db.add(policy)
        self.db.flush()

        # Log creation
        self._log_policy_change(
            policy=policy,
            change_type=PolicyChangeType.CREATED,
            new_configuration=configuration,
            change_summary=f"Created policy '{name}'",
            reason="Initial policy creation",
            changed_by=created_by,
        )

        # Validate policy
        self._validate_policy(policy)

        self.db.commit()
        return policy

    def update_policy(
        self,
        policy_id: str,
        configuration: Dict[str, Any],
        updated_by: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        effective_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        priority: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Policy]:
        """Update an existing policy"""
        policy = self.get_policy_by_id(policy_id)
        if not policy:
            return None

        old_configuration = policy.configuration.copy()

        # Update fields
        if name is not None:
            policy.name = name
        if description is not None:
            policy.description = description
        if effective_at is not None:
            policy.effective_at = effective_at
        if expires_at is not None:
            policy.expires_at = expires_at
        if priority is not None:
            policy.priority = priority
        if tags is not None:
            policy.tags = tags

        policy.configuration = configuration

        # Create version if configuration changed
        if configuration != old_configuration:
            self._create_policy_version(policy, old_configuration, configuration, updated_by)

        # Log update
        self._log_policy_change(
            policy=policy,
            change_type=PolicyChangeType.UPDATED,
            old_configuration=old_configuration,
            new_configuration=configuration,
            change_summary=f"Updated policy '{policy.name}'",
            reason="Policy configuration update",
            changed_by=updated_by,
        )

        # Validate policy
        self._validate_policy(policy)

        self.db.commit()
        return policy

    def activate_policy(self, policy_id: str, activated_by: User) -> Optional[Policy]:
        """Activate a policy"""
        policy = self.get_policy_by_id(policy_id)
        if not policy:
            return None

        old_status = policy.status
        policy.status = PolicyStatus.ACTIVE

        # Log activation
        self._log_policy_change(
            policy=policy,
            change_type=PolicyChangeType.ACTIVATED,
            change_summary=f"Activated policy '{policy.name}'",
            reason="Policy activation",
            changed_by=activated_by,
        )

        # Check for conflicts with other active policies
        self._check_policy_conflicts(policy)

        self.db.commit()
        return policy

    def deactivate_policy(self, policy_id: str, deactivated_by: User) -> Optional[Policy]:
        """Deactivate a policy"""
        policy = self.get_policy_by_id(policy_id)
        if not policy:
            return None

        old_status = policy.status
        policy.status = PolicyStatus.INACTIVE

        # Log deactivation
        self._log_policy_change(
            policy=policy,
            change_type=PolicyChangeType.DEACTIVATED,
            change_summary=f"Deactivated policy '{policy.name}'",
            reason="Policy deactivation",
            changed_by=deactivated_by,
        )

        self.db.commit()
        return policy

    # Policy Versioning
    def get_policy_versions(self, policy_id: str) -> List[PolicyVersion]:
        """Get all versions of a policy"""
        query = select(PolicyVersion).where(PolicyVersion.policy_id == policy_id).order_by(
            PolicyVersion.created_at.desc()
        )
        return list(self.db.execute(query).scalars().all())

    def rollback_policy(self, policy_id: str, version: str, rolled_back_by: User) -> Optional[Policy]:
        """Rollback policy to a specific version"""
        policy = self.get_policy_by_id(policy_id)
        if not policy:
            return None

        policy_version = self.db.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy_id,
                PolicyVersion.version == version,
            )
        ).scalar_one_or_none()

        if not policy_version:
            return None

        old_configuration = policy.configuration.copy()
        policy.configuration = policy_version.configuration

        # Log rollback
        self._log_policy_change(
            policy=policy,
            change_type=PolicyChangeType.ROLLED_BACK,
            old_configuration=old_configuration,
            new_configuration=policy_version.configuration,
            change_summary=f"Rolled back policy '{policy.name}' to version {version}",
            reason=f"Rollback to version {version}",
            changed_by=rolled_back_by,
        )

        self.db.commit()
        return policy

    # Policy Validation
    def validate_policy_configuration(
        self, policy_type: PolicyType, configuration: Dict[str, Any]
    ) -> List[str]:
        """Validate policy configuration against business rules"""
        errors = []

        if policy_type == PolicyType.PRICING:
            errors.extend(self._validate_pricing_policy(configuration))
        elif policy_type == PolicyType.DISCOUNT:
            errors.extend(self._validate_discount_policy(configuration))
        elif policy_type == PolicyType.PAYMENT_TERMS:
            errors.extend(self._validate_payment_terms_policy(configuration))
        elif policy_type == PolicyType.PRICE_FLOOR:
            errors.extend(self._validate_price_floor_policy(configuration))
        elif policy_type == PolicyType.SLA:
            errors.extend(self._validate_sla_policy(configuration))

        return errors

    # Policy Evaluation (for deals)
    def evaluate_policy_for_deal(self, deal: Deal) -> Dict[str, Any]:
        """Evaluate all active policies against a deal"""
        active_policies = self.get_policies(status=PolicyStatus.ACTIVE)

        results = {
            "passed": True,
            "violations": [],
            "required_stages": [],
            "applied_policies": [],
        }

        for policy in active_policies:
            try:
                if policy.policy_type == PolicyType.PRICING:
                    violation = self._evaluate_pricing_policy_for_deal(policy, deal)
                    if violation:
                        results["passed"] = False
                        results["violations"].append(violation)
                        results["applied_policies"].append(policy.name)
                elif policy.policy_type == PolicyType.SLA:
                    # Handle SLA policies
                    pass
            except Exception as e:
                # Log evaluation error but continue with other policies
                continue

        return results

    # Policy Simulation
    def simulate_policy_impact(
        self, policy_id: str, test_deals: List[Dict[str, Any]], simulated_by: User
    ) -> PolicySimulation:
        """Simulate policy impact against test data"""
        policy = self.get_policy_by_id(policy_id)
        if not policy:
            raise ValueError(f"Policy {policy_id} not found")

        simulation_results = []
        for test_deal in test_deals:
            # Create a mock deal for evaluation
            deal = Deal(
                amount=Decimal(str(test_deal.get("amount", 0))),
                discount_percent=Decimal(str(test_deal.get("discount_percent", 0))),
                payment_terms_days=test_deal.get("payment_terms_days", 30),
                risk=DealRisk(test_deal.get("risk", "medium")),
            )

            evaluation = self.evaluate_policy_for_deal(deal)
            simulation_results.append({
                "deal_id": test_deal.get("id"),
                "deal_name": test_deal.get("name"),
                "evaluation": evaluation,
            })

        simulation = PolicySimulation(
            policy_id=policy_id,
            simulation_type="impact_analysis",
            test_data=test_deals,
            results={"evaluations": simulation_results, "summary": self._summarize_simulation_results(simulation_results)},
            created_by_id=simulated_by.id,
        )

        self.db.add(simulation)
        self.db.commit()
        return simulation

    # Migration from JSON
    def migrate_json_policies(self, migrated_by: User) -> List[Policy]:
        """Migrate existing JSON policies to database"""
        migrated_policies = []

        if not POLICY_PATH.exists():
            return migrated_policies

        with POLICY_PATH.open(encoding="utf-8") as handle:
            json_policy = json.load(handle)

        # Create pricing policy from JSON
        pricing_policy = self.create_policy(
            name="Migrated Pricing Policy",
            policy_type=PolicyType.PRICING,
            configuration=json_policy,
            created_by=migrated_by,
            description="Migrated from JSON configuration",
            effective_at=datetime.fromisoformat(json_policy["effective_at"]),
        )

        # Activate the migrated policy
        self.activate_policy(pricing_policy.id, migrated_by)
        migrated_policies.append(pricing_policy)

        return migrated_policies

    # Private helper methods
    def _log_policy_change(
        self,
        policy: Policy,
        change_type: PolicyChangeType,
        changed_by: User,
        change_summary: str,
        reason: Optional[str] = None,
        old_configuration: Optional[Dict[str, Any]] = None,
        new_configuration: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a policy change"""
        change_log = PolicyChangeLog(
            policy_id=policy.id,
            change_type=change_type,
            old_configuration=old_configuration,
            new_configuration=new_configuration,
            change_summary=change_summary,
            reason=reason,
            changed_by_id=changed_by.id,
        )
        self.db.add(change_log)

    def _create_policy_version(
        self,
        policy: Policy,
        old_configuration: Dict[str, Any],
        new_configuration: Dict[str, Any],
        created_by: User,
    ) -> None:
        """Create a new policy version"""
        # Increment version number
        version_parts = policy.version.split(".")
        if len(version_parts) == 3:
            version_parts[-1] = str(int(version_parts[-1]) + 1)
        new_version = ".".join(version_parts)

        policy_version = PolicyVersion(
            policy_id=policy.id,
            version=new_version,
            configuration=old_configuration,
            change_summary=f"Updated from version {policy.version}",
            created_by_id=created_by.id,
        )

        self.db.add(policy_version)
        policy.version = new_version

    def _validate_policy(self, policy: Policy) -> None:
        """Validate policy and store validation results"""
        # Clear existing validations
        self.db.execute(
            select(PolicyValidation).where(PolicyValidation.policy_id == policy.id)
        ).scalars().delete()

        # Validate configuration
        errors = self.validate_policy_configuration(policy.policy_type, policy.configuration)

        if errors:
            for error in errors:
                validation = PolicyValidation(
                    policy_id=policy.id,
                    validation_type="configuration",
                    status="failed",
                    message=error,
                )
                self.db.add(validation)
        else:
            validation = PolicyValidation(
                policy_id=policy.id,
                validation_type="configuration",
                status="passed",
                message="Policy configuration is valid",
            )
            self.db.add(validation)

    def _check_policy_conflicts(self, policy: Policy) -> None:
        """Check for conflicts with other active policies"""
        active_policies = self.get_policies(
            policy_type=policy.policy_type, status=PolicyStatus.ACTIVE
        )

        for other_policy in active_policies:
            if other_policy.id == policy.id:
                continue

            # Check for configuration conflicts
            conflicts = self._detect_policy_conflicts(policy, other_policy)
            for conflict in conflicts:
                policy_conflict = PolicyConflict(
                    policy_1_id=policy.id,
                    policy_2_id=other_policy.id,
                    conflict_type=conflict["type"],
                    description=conflict["description"],
                    severity=conflict["severity"],
                    resolution_suggestion=conflict.get("suggestion"),
                )
                self.db.add(policy_conflict)

    def _detect_policy_conflicts(
        self, policy1: Policy, policy2: Policy
    ) -> List[Dict[str, Any]]:
        """Detect conflicts between two policies"""
        conflicts = []

        # Priority conflict
        if policy1.priority == policy2.priority:
            conflicts.append({
                "type": "priority",
                "description": f"Policies '{policy1.name}' and '{policy2.name}' have equal priority",
                "severity": "medium",
                "suggestion": "Adjust policy priorities to establish clear precedence",
            })

        # Configuration conflicts based on policy type
        if policy1.policy_type == PolicyType.PRICING and policy2.policy_type == PolicyType.PRICING:
            config1, config2 = policy1.configuration, policy2.configuration
            if (
                config1.get("discount_guardrails", {}).get("default_max_discount_percent")
                != config2.get("discount_guardrails", {}).get("default_max_discount_percent")
            ):
                conflicts.append({
                    "type": "configuration",
                    "description": f"Discount limits differ between policies",
                    "severity": "high",
                    "suggestion": "Ensure discount limits are consistent across pricing policies",
                })

        return conflicts

    def _validate_pricing_policy(self, configuration: Dict[str, Any]) -> List[str]:
        """Validate pricing policy configuration"""
        errors = []

        if "discount_guardrails" not in configuration:
            errors.append("Discount guardrails configuration is required")
        else:
            dg = configuration["discount_guardrails"]
            if "default_max_discount_percent" not in dg:
                errors.append("Default max discount percent is required")
            elif not 0 <= dg["default_max_discount_percent"] <= 100:
                errors.append("Default max discount percent must be between 0 and 100")

        if "payment_terms_guardrails" not in configuration:
            errors.append("Payment terms guardrails configuration is required")
        else:
            ptg = configuration["payment_terms_guardrails"]
            if "max_terms_days" not in ptg:
                errors.append("Max terms days is required")
            elif ptg["max_terms_days"] <= 0:
                errors.append("Max terms days must be positive")

        if "price_floor" not in configuration:
            errors.append("Price floor configuration is required")
        else:
            pf = configuration["price_floor"]
            if "min_amount" not in pf:
                errors.append("Minimum amount is required")
            elif pf["min_amount"] < 0:
                errors.append("Minimum amount must be non-negative")

        return errors

    def _validate_discount_policy(self, configuration: Dict[str, Any]) -> List[str]:
        """Validate discount policy configuration"""
        errors = []

        if "max_discount_percent" not in configuration:
            errors.append("Max discount percent is required")
        elif not 0 <= configuration["max_discount_percent"] <= 100:
            errors.append("Max discount percent must be between 0 and 100")

        if "risk_overrides" not in configuration:
            errors.append("Risk overrides configuration is required")

        return errors

    def _validate_payment_terms_policy(self, configuration: Dict[str, Any]) -> List[str]:
        """Validate payment terms policy configuration"""
        errors = []

        if "max_terms_days" not in configuration:
            errors.append("Max terms days is required")
        elif configuration["max_terms_days"] <= 0:
            errors.append("Max terms days must be positive")

        return errors

    def _validate_price_floor_policy(self, configuration: Dict[str, Any]) -> List[str]:
        """Validate price floor policy configuration"""
        errors = []

        if "min_amount" not in configuration:
            errors.append("Minimum amount is required")
        elif configuration["min_amount"] < 0:
            errors.append("Minimum amount must be non-negative")

        return errors

    def _validate_sla_policy(self, configuration: Dict[str, Any]) -> List[str]:
        """Validate SLA policy configuration"""
        errors = []

        if "touch_rate_target" not in configuration:
            errors.append("Touch rate target is required")
        elif not 0 <= configuration["touch_rate_target"] <= 1:
            errors.append("Touch rate target must be between 0 and 1")

        if "response_time_threshold" not in configuration:
            errors.append("Response time threshold is required")
        elif configuration["response_time_threshold"] <= 0:
            errors.append("Response time threshold must be positive")

        return errors

    def _evaluate_pricing_policy_for_deal(self, policy: Policy, deal: Deal) -> Optional[Dict[str, Any]]:
        """Evaluate pricing policy for a specific deal"""
        config = policy.configuration

        # Check discount limits
        dg = config.get("discount_guardrails", {})
        max_discount = dg.get("default_max_discount_percent", 25)

        # Risk-based overrides
        risk_overrides = dg.get("risk_overrides", {})
        if deal.risk.value in risk_overrides:
            max_discount = risk_overrides[deal.risk.value]

        if float(deal.discount_percent) > max_discount:
            return {
                "type": "discount_limit",
                "policy": policy.name,
                "message": f"Discount {deal.discount_percent}% exceeds limit of {max_discount}% for {deal.risk.value} risk",
                "severity": "high",
            }

        # Check price floor
        pf = config.get("price_floor", {})
        min_amount = pf.get("min_amount", 0)
        currency = pf.get("currency", "USD")

        if deal.currency == currency and float(deal.amount) < min_amount:
            return {
                "type": "price_floor",
                "policy": policy.name,
                "message": f"Amount ${deal.amount:,.2f} is below floor of ${min_amount:,.2f}",
                "severity": "medium",
            }

        # Check payment terms
        ptg = config.get("payment_terms_guardrails", {})
        max_terms = ptg.get("max_terms_days", 30)

        if deal.payment_terms_days > max_terms:
            return {
                "type": "payment_terms",
                "policy": policy.name,
                "message": f"Payment terms {deal.payment_terms_days} days exceed maximum of {max_terms} days",
                "severity": "medium",
            }

        return None

    def _summarize_simulation_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize simulation results"""
        total_deals = len(results)
        passed_deals = sum(1 for r in results if r["evaluation"]["passed"])
        failed_deals = total_deals - passed_deals

        violations = []
        for result in results:
            violations.extend(result["evaluation"]["violations"])

        violation_types = {}
        for violation in violations:
            vtype = violation["type"]
            violation_types[vtype] = violation_types.get(vtype, 0) + 1

        return {
            "total_deals": total_deals,
            "passed_deals": passed_deals,
            "failed_deals": failed_deals,
            "pass_rate": passed_deals / total_deals if total_deals > 0 else 0,
            "total_violations": len(violations),
            "violation_types": violation_types,
        }