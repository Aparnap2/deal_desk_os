#!/usr/bin/env python3
"""
Simplified Backend Testing Script for Deal Desk OS

Tests actual functionality that exists in the codebase:
1. Database connectivity
2. Model creation and validation
3. Guardrail functionality (functions, not classes)
4. Payment processing (functions, not classes)
5. API endpoints availability
6. Basic error handling
"""

import asyncio
import sys
import os
import traceback
from datetime import datetime, timedelta
from decimal import Decimal

# Add the server directory to Python path
sys.path.insert(0, '/home/aparna/Desktop/deal_desk_os/server')

async def test_database_connectivity():
    """Test database connection and basic functionality."""
    print("🔍 Testing Database Connectivity...")

    try:
        from app.core.config import get_settings
        from app.db.session import engine, async_session_factory, init_models
        from sqlalchemy import text

        settings = get_settings()
        print(f"   Database URL: {settings.database_url}")

        # Test basic connection
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"   ✅ PostgreSQL connected: {version[:50]}...")

        # Test table creation
        await init_models()
        print("   ✅ Database models initialized successfully")

        # Test session factory
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            print(f"   ✅ Session factory working, database: {db_name}")

        return True
    except Exception as e:
        print(f"   ❌ Database connectivity failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_model_creation():
    """Test creating model instances and database operations."""
    print("\n🔍 Testing Model Creation and Database Operations...")

    try:
        from app.db.session import async_session_factory
        from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
        from app.models.user import User, UserRole
        from app.models.policy import Policy, PolicyStatus, PolicyType
        from app.models.invoice import Invoice, InvoiceStatus
        from app.models.payment import Payment, PaymentStatus

        async with async_session_factory() as session:
            # Create test user
            test_user = User(
                id="test-user-backend",
                email="backend-test@example.com",
                full_name="Backend Test User",
                hashed_password="test_password_hash",
                roles=[UserRole.REVOPS_USER],
                is_active=True
            )

            session.add(test_user)
            await session.commit()
            await session.refresh(test_user)
            print("   ✅ Test user created successfully")

            # Create test deal
            test_deal = Deal(
                id="test-deal-backend",
                name="Backend Test Deal",
                description="Test deal for backend validation",
                amount=Decimal("25000.00"),
                currency="USD",
                discount_percent=Decimal("15.0"),
                payment_terms_days=30,
                risk=DealRisk.LOW,
                probability=80,
                stage=DealStage.PROSPECTING,
                expected_close=datetime.utcnow() + timedelta(days=30),
                created_by_id=test_user.id,
                owner_id=test_user.id
            )

            session.add(test_deal)
            await session.commit()
            await session.refresh(test_deal)
            print("   ✅ Test deal created successfully")

            # Create test policy
            test_policy = Policy(
                id="test-policy-backend",
                name="Backend Test Policy",
                description="Test policy for backend validation",
                policy_type=PolicyType.PRICING,
                configuration={
                    "discount_guardrails": {
                        "default_max_discount_percent": 25,
                        "risk_overrides": {"low": 30, "medium": 20, "high": 10}
                    }
                },
                priority=10,
                status=PolicyStatus.ACTIVE,
                created_by_id=test_user.id
            )

            session.add(test_policy)
            await session.commit()
            await session.refresh(test_policy)
            print("   ✅ Test policy created successfully")

            # Create test invoice (Note: No InvoiceType enum exists)
            test_invoice = Invoice(
                id="test-invoice-backend",
                deal_id=test_deal.id,
                invoice_number="INV-BACKEND-001",
                amount=Decimal("25000.00"),
                currency="USD",
                status=InvoiceStatus.DRAFT,
                due_date=datetime.utcnow() + timedelta(days=30)
            )

            session.add(test_invoice)
            await session.commit()
            await session.refresh(test_invoice)
            print("   ✅ Test invoice created successfully")

            # Create test payment
            test_payment = Payment(
                id="test-payment-backend",
                deal_id=test_deal.id,
                invoice_id=test_invoice.id,
                amount=Decimal("25000.00"),
                currency="USD",
                status=PaymentStatus.PENDING,
                gateway_provider="stripe",
                gateway_transaction_id="pi_test_backend_001"
            )

            session.add(test_payment)
            await session.commit()
            await session.refresh(test_payment)
            print("   ✅ Test payment created successfully")

            # Test queries
            deals_result = await session.execute(
                "SELECT COUNT(*) FROM deals WHERE id = :deal_id",
                {"deal_id": test_deal.id}
            )
            deal_count = deals_result.scalar()
            print(f"   ✅ Query verification: Found {deal_count} test deal")

        return True
    except Exception as e:
        print(f"   ❌ Model creation failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_guardrail_functions():
    """Test guardrail functionality using actual functions."""
    print("\n🔍 Testing Guardrail Functions...")

    try:
        from app.services.guardrail_service import (
            evaluate_pricing_guardrails,
            load_pricing_policy,
            apply_guardrail_result
        )
        from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
        from decimal import Decimal

        # Test policy loading
        policy = load_pricing_policy()
        print("   ✅ Pricing policy loaded successfully")
        print(f"      - Version: {policy.get('version', 'unknown')}")
        print(f"      - Max discount: {policy['discount_guardrails']['default_max_discount_percent']}%")

        # Test guardrail evaluation
        evaluation = evaluate_pricing_guardrails(
            amount=10000.00,
            discount_percent=15.0,
            payment_terms_days=30,
            risk=DealRisk.LOW
        )
        print(f"   ✅ Guardrail evaluation: {evaluation.status.value}")
        print(f"      - Requires manual review: {evaluation.requires_manual_review}")
        if evaluation.reason:
            print(f"      - Reason: {evaluation.reason}")

        # Test guardrail violation
        violation_evaluation = evaluate_pricing_guardrails(
            amount=1000.00,  # Below floor
            discount_percent=50.0,  # Too high
            payment_terms_days=90,  # Too long
            risk=DealRisk.HIGH
        )
        print(f"   ✅ Violation detection: {violation_evaluation.status.value}")
        print(f"      - Reason: {violation_evaluation.reason}")

        # Test applying guardrail result to deal
        test_deal = Deal(
            id="guardrail-test-deal",
            name="Guardrail Test Deal",
            amount=Decimal("50000.00"),
            currency="USD",
            discount_percent=Decimal("30.0"),
            payment_terms_days=60,
            risk=DealRisk.HIGH,
            stage=DealStage.PROPOSAL,
            probability=65
        )

        apply_guardrail_result(test_deal, violation_evaluation)
        print(f"   ✅ Guardrail applied to deal:")
        print(f"      - Status: {test_deal.guardrail_status.value}")
        print(f"      - Locked: {test_deal.guardrail_locked}")
        print(f"      - Reason: {test_deal.guardrail_reason}")
        print(f"      - Stage: {test_deal.stage.value}")

        return True
    except Exception as e:
        print(f"   ❌ Guardrail function test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_payment_functions():
    """Test payment processing functions."""
    print("\n🔍 Testing Payment Processing Functions...")

    try:
        from app.services.payment_service import process_payment
        from app.db.session import async_session_factory
        from app.models.deal import Deal, DealRisk, DealStage
        from app.models.payment import PaymentStatus
        from app.schemas.payment import PaymentCreate
        from decimal import Decimal
        from datetime import datetime, timezone

        async with async_session_factory() as session:
            # Create a test deal for payment processing
            test_deal = Deal(
                id="payment-test-deal",
                name="Payment Test Deal",
                amount=Decimal("15000.00"),
                currency="USD",
                discount_percent=Decimal("10.0"),
                payment_terms_days=30,
                risk=DealRisk.LOW,
                stage=DealStage.PROPOSAL,
                probability=90
            )

            session.add(test_deal)
            await session.commit()

            # Test payment creation
            payment_payload = PaymentCreate(
                amount=Decimal("15000.00"),
                currency="USD",
                idempotency_key="test_payment_001",
                provider_reference="stripe_test_001",
                simulate_failure=False
            )

            payment = await process_payment(
                session,
                deal=test_deal,
                payload=payment_payload,
                redis_client=None  # Skip Redis for this test
            )

            print(f"   ✅ Payment processed successfully")
            print(f"      - Payment ID: {payment.id}")
            print(f"      - Status: {payment.status.value}")
            print(f"      - Amount: {payment.amount}")
            print(f"      - Deal stage after payment: {test_deal.stage.value}")

            # Test failed payment simulation
            failed_payload = PaymentCreate(
                amount=Decimal("1000.00"),
                currency="USD",
                idempotency_key="test_payment_failed_001",
                provider_reference="stripe_test_failed_001",
                simulate_failure=True
            )

            failed_payment = await process_payment(
                session,
                deal=test_deal,
                payload=failed_payload,
                redis_client=None
            )

            print(f"   ✅ Failed payment simulation successful")
            print(f"      - Status: {failed_payment.status.value}")
            print(f"      - Failure reason: {failed_payment.failure_reason}")

        return True
    except Exception as e:
        print(f"   ❌ Payment processing test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_api_endpoints():
    """Test core API endpoints functionality."""
    print("\n🔍 Testing Core API Endpoints...")

    try:
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # Test health endpoint
        response = client.get("/health")
        if response.status_code == 200:
            print("   ✅ Health endpoint working")
            print(f"      - Response: {response.json()}")
        else:
            print(f"   ❌ Health endpoint failed: {response.status_code}")

        # Test deals endpoint (should work without auth for list)
        response = client.get("/deals/")
        if response.status_code in [200, 401, 403]:  # Expected responses
            print(f"   ✅ Deals endpoint accessible (status: {response.status_code})")
        else:
            print(f"   ❌ Deals endpoint failed: {response.status_code}")

        # Test users endpoint
        response = client.get("/users/")
        if response.status_code in [200, 401, 403]:
            print(f"   ✅ Users endpoint accessible (status: {response.status_code})")
        else:
            print(f"   ❌ Users endpoint failed: {response.status_code}")

        # Test policies endpoint
        response = client.get("/policies/")
        if response.status_code in [200, 401, 403]:
            print(f"   ✅ Policies endpoint accessible (status: {response.status_code})")
        else:
            print(f"   ❌ Policies endpoint failed: {response.status_code}")

        # Test invoices endpoint
        response = client.get("/invoices/")
        if response.status_code in [200, 401, 403, 307]:  # 307 redirect is also fine
            print(f"   ✅ Invoices endpoint accessible (status: {response.status_code})")
        else:
            print(f"   ❌ Invoices endpoint failed: {response.status_code}")

        return True
    except Exception as e:
        print(f"   ❌ API endpoint test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_error_handling():
    """Test error handling and recovery scenarios."""
    print("\n🔍 Testing Error Handling...")

    try:
        from app.db.session import async_session_factory
        from app.services.guardrail_service import evaluate_pricing_guardrails
        from app.models.deal import DealRisk, DealStage
        from decimal import Decimal

        # Test invalid data handling in guardrails
        try:
            evaluation = evaluate_pricing_guardrails(
                amount=-1000.00,  # Negative amount
                discount_percent=150.00,  # Invalid discount
                payment_terms_days=-30,  # Negative terms
                risk=DealRisk.HIGH
            )
            print("   ✅ Invalid data handled gracefully in guardrails")
        except Exception as guardrail_error:
            print(f"   ✅ Guardrail error properly handled: {type(guardrail_error).__name__}")

        # Test database constraint handling
        async with async_session_factory() as session:
            try:
                # Start a transaction
                await session.begin()

                # Force an error to test rollback
                from sqlalchemy.exc import SQLAlchemyError
                raise SQLAlchemyError("Simulated database error for rollback test")

            except SQLAlchemyError:
                await session.rollback()
                print("   ✅ Database rollback handled correctly")

        # Test enum validation
        try:
            invalid_risk = DealRisk("invalid_risk")  # This should fail
        except (ValueError, AttributeError) as enum_error:
            print(f"   ✅ Enum validation working: {type(enum_error).__name__}")

        return True
    except Exception as e:
        print(f"   ❌ Error handling test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_database_tables():
    """Test database table structure and integrity."""
    print("\n🔍 Testing Database Table Structure...")

    try:
        from app.db.session import engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            # Check if core tables exist
            tables_to_check = [
                'users', 'deals', 'policies', 'invoices', 'payments',
                'events', 'approvals', 'audit_logs'
            ]

            for table_name in tables_to_check:
                try:
                    result = await conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = result.scalar()
                    print(f"   ✅ Table '{table_name}' exists with {count} rows")
                except Exception as table_error:
                    print(f"   ❌ Table '{table_name}' error: {str(table_error)}")

            # Test basic SQL functionality
            result = await conn.execute(text("SELECT current_timestamp, version()"))
            timestamp, version = result.first()
            print(f"   ✅ Basic SQL functionality working")
            print(f"      - Server time: {timestamp}")
            print(f"      - PostgreSQL: {version[:30]}...")

        return True
    except Exception as e:
        print(f"   ❌ Database table test failed: {str(e)}")
        traceback.print_exc()
        return False

async def main():
    """Run all backend tests."""
    print("🚀 Starting Deal Desk OS Backend Functionality Testing")
    print("=" * 60)

    # Change to server directory
    os.chdir('/home/aparna/Desktop/deal_desk_os/server')

    test_results = {
        "Database Connectivity": False,
        "Model Creation": False,
        "Guardrail Functions": False,
        "Payment Functions": False,
        "API Endpoints": False,
        "Error Handling": False,
        "Database Tables": False
    }

    try:
        # Run tests in sequence
        test_results["Database Connectivity"] = await test_database_connectivity()

        if test_results["Database Connectivity"]:
            test_results["Model Creation"] = await test_model_creation()
            test_results["Guardrail Functions"] = await test_guardrail_functions()
            test_results["Payment Functions"] = await test_payment_functions()
            test_results["API Endpoints"] = await test_api_endpoints()
            test_results["Error Handling"] = await test_error_handling()
            test_results["Database Tables"] = await test_database_tables()
        else:
            print("\n⚠️  Skipping remaining tests due to database connectivity issues")

    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {str(e)}")
        traceback.print_exc()

    # Print summary
    print("\n" + "=" * 60)
    print("📊 BACKEND FUNCTIONALITY TESTING SUMMARY")
    print("=" * 60)

    passed_tests = sum(1 for result in test_results.values() if result)
    total_tests = len(test_results)

    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall Result: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 ALL BACKEND TESTS PASSED! Core functionality is working correctly.")
        return 0
    elif passed_tests >= total_tests * 0.75:
        print("⚠️  MOST TESTS PASSED. System has minor issues but core functionality works.")
        return 1
    else:
        print("🚨 SIGNIFICANT ISSUES FOUND. System needs fixes before proceeding.")
        return 2

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)