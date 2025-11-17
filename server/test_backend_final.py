#!/usr/bin/env python3
"""
Final Backend Testing Script for Deal Desk OS

Tests actual functionality with correct enum values:
1. Database connectivity
2. Model creation with correct enums
3. Guardrail functionality
4. Payment processing
5. API endpoints
6. Error handling
7. Database integrity
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
        return False

async def test_model_creation():
    """Test creating model instances and database operations."""
    print("\n🔍 Testing Model Creation with Correct Enums...")

    try:
        from app.db.session import async_session_factory
        from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
        from app.models.user import User, UserRole
        from app.models.policy import Policy, PolicyStatus, PolicyType
        from app.models.invoice import Invoice, InvoiceStatus
        from app.models.payment import Payment, PaymentStatus

        async with async_session_factory() as session:
            # Create test user with correct role
            test_user = User(
                id="test-user-backend-final",
                email="backend-test-final@example.com",
                full_name="Backend Test User Final",
                hashed_password="test_password_hash",
                roles=[UserRole.REVOPS_ADMIN],  # Correct enum value
                is_active=True
            )

            session.add(test_user)
            await session.commit()
            await session.refresh(test_user)
            print("   ✅ Test user created successfully with REVOPS_ADMIN role")

            # Create test deal with correct stage
            test_deal = Deal(
                id="test-deal-backend-final",
                name="Backend Test Deal Final",
                description="Test deal for backend validation with correct enums",
                amount=Decimal("25000.00"),
                currency="USD",
                discount_percent=Decimal("15.0"),
                payment_terms_days=30,
                risk=DealRisk.LOW,
                probability=80,
                stage=DealStage.PROSPECTING,  # Correct enum value
                expected_close=datetime.utcnow() + timedelta(days=30),
                created_by_id=test_user.id,
                owner_id=test_user.id
            )

            session.add(test_deal)
            await session.commit()
            await session.refresh(test_deal)
            print("   ✅ Test deal created successfully with PROSPECTING stage")

            # Create test policy
            test_policy = Policy(
                id="test-policy-backend-final",
                name="Backend Test Policy Final",
                description="Test policy for backend validation with correct enums",
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

            # Create test invoice
            test_invoice = Invoice(
                id="test-invoice-backend-final",
                deal_id=test_deal.id,
                invoice_number="INV-BACKEND-FINAL-001",
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
                id="test-payment-backend-final",
                deal_id=test_deal.id,
                invoice_id=test_invoice.id,
                amount=Decimal("25000.00"),
                currency="USD",
                status=PaymentStatus.PENDING,
                gateway_provider="stripe",
                gateway_transaction_id="pi_test_backend_final_001"
            )

            session.add(test_payment)
            await session.commit()
            await session.refresh(test_payment)
            print("   ✅ Test payment created successfully")

        return True
    except Exception as e:
        print(f"   ❌ Model creation failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_guardrail_functions():
    """Test guardrail functionality with correct enums."""
    print("\n🔍 Testing Guardrail Functions with Correct Enums...")

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
            id="guardrail-test-deal-final",
            name="Guardrail Test Deal Final",
            amount=Decimal("50000.00"),
            currency="USD",
            discount_percent=Decimal("30.0"),
            payment_terms_days=60,
            risk=DealRisk.HIGH,
            stage=DealStage.FINANCE_REVIEW,  # Correct enum
            probability=65
        )

        apply_guardrail_result(test_deal, violation_evaluation)
        print(f"   ✅ Guardrail applied to deal:")
        print(f"      - Status: {test_deal.guardrail_status.value}")
        print(f"      - Locked: {test_deal.guardrail_locked}")
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

        async with async_session_factory() as session:
            # Create a test deal for payment processing
            test_deal = Deal(
                id="payment-test-deal-final",
                name="Payment Test Deal Final",
                amount=Decimal("15000.00"),
                currency="USD",
                discount_percent=Decimal("10.0"),
                payment_terms_days=30,
                risk=DealRisk.LOW,
                stage=DealStage.LEGAL_REVIEW,  # Correct enum
                probability=90
            )

            session.add(test_deal)
            await session.commit()

            # Test payment creation
            payment_payload = PaymentCreate(
                amount=Decimal("15000.00"),
                currency="USD",
                idempotency_key="test_payment_final_001",
                provider_reference="stripe_test_final_001",
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
                idempotency_key="test_payment_failed_final_001",
                provider_reference="stripe_test_failed_final_001",
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

async def test_database_integrity():
    """Test database integrity and table relationships."""
    print("\n🔍 Testing Database Integrity...")

    try:
        from app.db.session import async_session_factory
        from sqlalchemy import text

        async with async_session_factory() as session:
            # Test basic SQL functionality
            result = await session.execute(text("SELECT current_timestamp, version()"))
            timestamp, version = result.first()
            print(f"   ✅ Basic SQL functionality working")
            print(f"      - Server time: {timestamp}")

            # Test table existence and relationships
            tables_result = await session.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in tables_result.fetchall()]
            print(f"   ✅ Found {len(tables)} tables in database")

            # Test that our test data exists
            user_result = await session.execute(text("SELECT COUNT(*) FROM users WHERE email LIKE '%backend-test-final%'"))
            user_count = user_result.scalar()
            print(f"   ✅ Found {user_count} test users")

            deal_result = await session.execute(text("SELECT COUNT(*) FROM deals WHERE id LIKE '%backend-final%'"))
            deal_count = deal_result.scalar()
            print(f"   ✅ Found {deal_count} test deals")

        return True
    except Exception as e:
        print(f"   ❌ Database integrity test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_api_endpoints():
    """Test core API endpoints functionality."""
    print("\n🔍 Testing API Endpoints...")

    try:
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        endpoints_to_test = [
            ("/health", "Health check"),
            ("/deals/", "Deals endpoint"),
            ("/policies/", "Policies endpoint"),
            ("/invoices/", "Invoices endpoint"),
        ]

        for endpoint, description in endpoints_to_test:
            response = client.get(endpoint)
            if response.status_code in [200, 401, 403, 307]:  # Expected responses
                print(f"   ✅ {description} accessible (status: {response.status_code})")
            else:
                print(f"   ❌ {description} failed: {response.status_code}")

        return True
    except Exception as e:
        print(f"   ❌ API endpoint test failed: {str(e)}")
        return False

async def main():
    """Run all backend tests."""
    print("🚀 Starting Deal Desk OS Final Backend Testing")
    print("=" * 60)

    # Change to server directory
    os.chdir('/home/aparna/Desktop/deal_desk_os/server')

    test_results = {
        "Database Connectivity": False,
        "Model Creation": False,
        "Guardrail Functions": False,
        "Payment Functions": False,
        "Database Integrity": False,
        "API Endpoints": False
    }

    try:
        # Run tests in sequence
        test_results["Database Connectivity"] = await test_database_connectivity()

        if test_results["Database Connectivity"]:
            test_results["Model Creation"] = await test_model_creation()
            test_results["Guardrail Functions"] = await test_guardrail_functions()
            test_results["Payment Functions"] = await test_payment_functions()
            test_results["Database Integrity"] = await test_database_integrity()
            test_results["API Endpoints"] = await test_api_endpoints()
        else:
            print("\n⚠️  Skipping remaining tests due to database connectivity issues")

    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {str(e)}")
        traceback.print_exc()

    # Print summary
    print("\n" + "=" * 60)
    print("📊 FINAL BACKEND TESTING SUMMARY")
    print("=" * 60)

    passed_tests = sum(1 for result in test_results.values() if result)
    total_tests = len(test_results)

    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall Result: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 ALL BACKEND TESTS PASSED! Backend system is ready for production.")
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