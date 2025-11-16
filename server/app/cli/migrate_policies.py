#!/usr/bin/env python3
"""
CLI script to migrate existing JSON policies to the database
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime

import click
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.models.user import User, UserRole
from app.services.policy_service import PolicyService

POLICY_PATH = Path(__file__).resolve().parents[3] / "shared" / "policies" / "pricing_policy_v1.json"


@click.group()
def cli():
    """Policy migration CLI tool"""
    pass


@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be migrated without actually doing it')
@click.option('--force', is_flag=True, help='Force migration even if policies already exist')
def migrate(dry_run: bool, force: bool):
    """Migrate JSON policies to database"""
    db = SessionLocal()

    try:
        # Find or create system user
        system_user = _get_or_create_system_user(db)

        # Check if policies already exist
        existing_policies = db.query(Policy).filter(Policy.policy_type == PolicyType.PRICING).count()
        if existing_policies > 0 and not force:
            click.echo(f"Found {existing_policies} existing pricing policies. Use --force to override.")
            return

        # Load JSON policy
        if not POLICY_PATH.exists():
            click.echo(f"JSON policy file not found: {POLICY_PATH}")
            return

        with open(POLICY_PATH, 'r') as f:
            json_policy = json.load(f)

        click.echo(f"Loaded policy from {POLICY_PATH}")
        click.echo(f"Policy version: {json_policy.get('version')}")
        click.echo(f"Effective date: {json_policy.get('effective_at')}")

        if dry_run:
            click.echo("\n--- DRY RUN MODE ---")
            click.echo("Would create the following policies:")
            click.echo(f"1. Pricing Policy: '{json_policy}'")
            return

        # Create policy service
        service = PolicyService(db)

        # Create pricing policy from JSON
        pricing_policy = service.create_policy(
            name="Migrated Pricing Policy",
            policy_type=PolicyType.PRICING,
            configuration=json_policy,
            created_by=system_user,
            description="Migrated from JSON configuration",
            effective_at=datetime.fromisoformat(json_policy["effective_at"]),
            tags=["migrated", "json-import"],
        )

        # Activate the migrated policy
        service.activate_policy(pricing_policy.id, system_user)

        click.echo(f"\n✅ Successfully migrated policy:")
        click.echo(f"   ID: {pricing_policy.id}")
        click.echo(f"   Name: {pricing_policy.name}")
        click.echo(f"   Type: {pricing_policy.policy_type}")
        click.echo(f"   Status: {pricing_policy.status}")
        click.echo(f"   Version: {pricing_policy.version}")

    except Exception as e:
        click.echo(f"❌ Migration failed: {e}", err=True)
        db.rollback()
        raise
    finally:
        db.close()


@cli.command()
@click.option('--policy-id', help='Specific policy ID to validate')
def validate(policy_id: str):
    """Validate migrated policies"""
    db = SessionLocal()

    try:
        service = PolicyService(db)

        if policy_id:
            # Validate specific policy
            policy = service.get_policy_by_id(policy_id)
            if not policy:
                click.echo(f"Policy not found: {policy_id}")
                return

            errors = service.validate_policy_configuration(policy.policy_type, policy.configuration)
            if errors:
                click.echo(f"❌ Policy '{policy.name}' has validation errors:")
                for error in errors:
                    click.echo(f"  - {error}")
            else:
                click.echo(f"✅ Policy '{policy.name}' is valid")
        else:
            # Validate all policies
            policies = service.get_policies()
            click.echo(f"Validating {len(policies)} policies...")

            valid_count = 0
            invalid_count = 0

            for policy in policies:
                errors = service.validate_policy_configuration(policy.policy_type, policy.configuration)
                if errors:
                    click.echo(f"❌ Policy '{policy.name}' ({policy.policy_type}):")
                    for error in errors:
                        click.echo(f"  - {error}")
                    invalid_count += 1
                else:
                    valid_count += 1

            click.echo(f"\nSummary: {valid_count} valid, {invalid_count} invalid policies")

    except Exception as e:
        click.echo(f"❌ Validation failed: {e}", err=True)
        raise
    finally:
        db.close()


@cli.command()
@click.option('--policy-id', help='Specific policy ID to test')
@click.option('--sample-size', default=5, help='Number of sample deals to test against')
def test(policy_id: str, sample_size: int):
    """Test policy evaluation against sample deals"""
    db = SessionLocal()

    try:
        service = PolicyService(db)

        if policy_id:
            # Test specific policy
            policy = service.get_policy_by_id(policy_id)
            if not policy:
                click.echo(f"Policy not found: {policy_id}")
                return

            # Generate sample test deals
            test_deals = [
                {
                    "name": f"Test Deal {i+1}",
                    "amount": 10000 + (i * 5000),
                    "discount_percent": 5 + (i * 2),
                    "payment_terms_days": 30 + (i * 10),
                    "risk": ["low", "medium", "high"][i % 3],
                }
                for i in range(sample_size)
            ]

            click.echo(f"Testing policy '{policy.name}' against {len(test_deals)} sample deals...")

            simulation = service.simulate_policy_impact(policy_id, test_deals, _get_or_create_system_user(db))

            results = simulation.results
            summary = results.get("summary", {})

            click.echo(f"\nResults:")
            click.echo(f"  Total deals: {summary.get('total_deals', 0)}")
            click.echo(f"  Passed: {summary.get('passed_deals', 0)}")
            click.echo(f"  Failed: {summary.get('failed_deals', 0)}")
            click.echo(f"  Pass rate: {summary.get('pass_rate', 0):.1%}")
            click.echo(f"  Total violations: {summary.get('total_violations', 0)}")

            if summary.get('violation_types'):
                click.echo("\nViolation types:")
                for vtype, count in summary['violation_types'].items():
                    click.echo(f"  {vtype}: {count}")

    except Exception as e:
        click.echo(f"❌ Test failed: {e}", err=True)
        raise
    finally:
        db.close()


@cli.command()
def cleanup():
    """Clean up old migrated policies"""
    db = SessionLocal()

    try:
        # Find old migrated policies
        old_policies = db.query(Policy).filter(
            Policy.tags.contains(['migrated']),
            Policy.status == PolicyStatus.SUPERSEDED
        ).all()

        if not old_policies:
            click.echo("No old migrated policies found to clean up")
            return

        click.echo(f"Found {len(old_policies)} old migrated policies to clean up:")

        for policy in old_policies:
            click.echo(f"  - {policy.name} ({policy.id})")

        # Ask for confirmation
        if click.confirm('Do you want to delete these old policies?'):
            for policy in old_policies:
                db.delete(policy)
            db.commit()
            click.echo(f"✅ Cleaned up {len(old_policies)} old policies")

    except Exception as e:
        click.echo(f"❌ Cleanup failed: {e}", err=True)
        db.rollback()
        raise
    finally:
        db.close()


def _get_or_create_system_user(db: Session) -> User:
    """Get or create the system user for migrations"""
    system_user = db.query(User).filter(User.email == "system@deal-desk.local").first()

    if not system_user:
        system_user = User(
            email="system@deal-desk.local",
            full_name="System User",
            hashed_password="system",  # Not used for system user
            roles=[UserRole.ADMIN, UserRole.REVOPS_ADMIN],
            is_active=True,
        )
        db.add(system_user)
        db.commit()
        db.refresh(system_user)

    return system_user


if __name__ == '__main__':
    cli()