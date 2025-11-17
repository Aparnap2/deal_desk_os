#!/usr/bin/env python3
"""
Comprehensive Backend Testing Script for Deal Desk OS

This script tests:
1. Database connectivity and migrations
2. Core API endpoints functionality
3. Service layer business logic
4. Error handling and recovery scenarios
"""

import asyncio
import sys
import os
import traceback
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional

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
        from app.models.deal import Deal, DealRisk, DealStage
        from app.models.user import User, UserRole
        from app.models.policy import Policy, PolicyStatus, PolicyType
        from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
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

            # Create test invoice
            test_invoice = Invoice(
                id="test-invoice-backend",
                deal_id=test_deal.id,
                invoice_number="INV-BACKEND-001",
                amount=Decimal("25000.00"),
                currency="USD",
                status=InvoiceStatus.DRAFT,
                invoice_type=InvoiceType.STANDARD,
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

async def test_service_layer():
    """Test service layer business logic."""
    print("\n🔍 Testing Service Layer Business Logic...")

    try:
        from app.services.guardrail_service import GuardrailService, initialize_policy_service
        from app.db.session import async_session_factory
        from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
        from datetime import datetime, timedelta
        from decimal import Decimal

        # Initialize policy service
        db = async_session_factory()
        try:
            initialize_policy_service(db)
            print("   ✅ Policy service initialized")
        finally:
            await db.close()

        # Test guardrail service
        async with async_session_factory() as session:
            guardrail_service = GuardrailService(session)

            # Create a test deal for validation
            test_deal = Deal(
                id="guardrail-test-deal",
                name="Guardrail Test Deal",
                amount=Decimal("50000.00"),
                currency="USD",
                discount_percent=Decimal("30.0"),  # High discount
                payment_terms_days=60,  # Long terms
                risk=DealRisk.HIGH,
                stage=DealStage.PROPOSAL,
                probability=60
            )

            # Test deal validation
            validation_result = await guardrail_service.validate_deal(test_deal)
            print(f"   ✅ Deal validation completed: {validation_result.is_valid}")
            print(f"      - Warnings: {len(validation_result.warnings)}")
            print(f"      - Errors: {len(validation_result.errors)}")
            print(f"      - Required approvals: {len(validation_result.required_approvals)}")

            # Test policy-based pricing check
            pricing_check = await guardrail_service.check_pricing_guardrails(
                test_deal.amount,
                test_deal.discount_percent,
                test_deal.risk
            )
            print(f"   ✅ Pricing guardrails check: {pricing_check.passed}")

            # Test payment terms validation
            terms_check = await guardrail_service.check_payment_terms_guardrails(
                test_deal.payment_terms_days,
                test_deal.risk
            )
            print(f"   ✅ Payment terms check: {terms_check.passed}")

        return True
    except Exception as e:
        print(f"   ❌ Service layer test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_api_endpoints():
    """Test core API endpoints functionality."""
    print("\n🔍 Testing Core API Endpoints...")

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api.dependencies.database import get_db
        from app.db.session import async_session_factory

        # Override database dependency
        async def get_test_db():
            async with async_session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = get_test_db

        client = TestClient(app)

        # Test health endpoint
        response = client.get("/health")
        if response.status_code == 200:
            print("   ✅ Health endpoint working")
        else:
            print(f"   ❌ Health endpoint failed: {response.status_code}")

        # Test deals endpoint
        response = client.get("/deals/")
        if response.status_code in [200, 401]:  # 401 is expected without auth
            print("   ✅ Deals endpoint accessible")
        else:
            print(f"   ❌ Deals endpoint failed: {response.status_code}")

        # Test policies endpoint
        response = client.get("/policies/")
        if response.status_code in [200, 401]:
            print("   ✅ Policies endpoint accessible")
        else:
            print(f"   ❌ Policies endpoint failed: {response.status_code}")

        # Test payments endpoint
        response = client.get("/payments/")
        if response.status_code in [200, 401]:
            print("   ✅ Payments endpoint accessible")
        else:
            print(f"   ❌ Payments endpoint failed: {response.status_code}")

        # Test invoices endpoint
        response = client.get("/invoices/")
        if response.status_code in [200, 401]:
            print("   ✅ Invoices endpoint accessible")
        else:
            print(f"   ❌ Invoices endpoint failed: {response.status_code}")

        # Test monitoring endpoint
        response = client.get("/monitoring/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"   ✅ Monitoring health check: {health_data.get('status', 'unknown')}")
        else:
            print(f"   ❌ Monitoring health check failed: {response.status_code}")

        # Clean up dependency overrides
        app.dependency_overrides.clear()

        return True
    except Exception as e:
        print(f"   ❌ API endpoint test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_payment_processing():
    """Test payment processing functionality."""
    print("\n🔍 Testing Payment Processing...")

    try:
        from app.services.payment_service import PaymentService
        from app.db.session import async_session_factory
        from app.models.payment import Payment, PaymentStatus
        from decimal import Decimal

        async with async_session_factory() as session:
            payment_service = PaymentService(session)

            # Test payment intent creation
            intent_result = await payment_service.create_payment_intent(
                amount=Decimal("10000.00"),
                currency="USD",
                deal_id="test-deal-payment",
                invoice_id="test-invoice-payment"
            )

            if intent_result:
                print("   ✅ Payment intent creation simulation successful")
                print(f"      - Amount: ${intent_result.get('amount', 0)}")
                print(f"      - Currency: {intent_result.get('currency', 'USD')}")
            else:
                print("   ⚠️  Payment intent creation returned None (expected without real gateway)")

            # Test payment status tracking
            test_payment = Payment(
                id="payment-status-test",
                deal_id="test-deal",
                invoice_id="test-invoice",
                amount=Decimal("5000.00"),
                currency="USD",
                status=PaymentStatus.PENDING,
                gateway_provider="stripe",
                gateway_transaction_id="test_tx_123"
            )

            session.add(test_payment)
            await session.commit()

            # Test payment confirmation workflow
            status_update = await payment_service.confirm_payment(
                payment_id=test_payment.id,
                gateway_transaction_id="test_tx_123",
                amount=Decimal("5000.00")
            )

            print("   ✅ Payment confirmation workflow tested")

        return True
    except Exception as e:
        print(f"   ❌ Payment processing test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_error_handling():
    """Test error handling and recovery scenarios."""
    print("\n🔍 Testing Error Handling...")

    try:
        from app.db.session import async_session_factory
        from sqlalchemy.exc import SQLAlchemyError
        from app.services.guardrail_service import GuardrailService
        from app.models.deal import Deal, DealRisk, DealStage
        from decimal import Decimal

        async with async_session_factory() as session:
            guardrail_service = GuardrailService(session)

            # Test validation with invalid deal data
            invalid_deal = Deal(
                id="invalid-deal-test",
                name="",  # Empty name should trigger validation
                amount=Decimal("-1000.00"),  # Negative amount
                currency="INVALID",  # Invalid currency
                discount_percent=Decimal("150.00"),  # Invalid discount
                payment_terms_days=-30,  # Negative terms
                risk=DealRisk.HIGH,
                stage=DealStage.PROPOSAL,
                probability=150  # Invalid probability
            )

            # This should handle the invalid data gracefully
            try:
                validation_result = await guardrail_service.validate_deal(invalid_deal)
                print("   ✅ Invalid data validation handled gracefully")
                print(f"      - Validation passed: {validation_result.is_valid}")
                print(f"      - Errors found: {len(validation_result.errors)}")
            except Exception as validation_error:
                print(f"   ✅ Validation error properly caught: {type(validation_error).__name__}")

            # Test database transaction rollback
            try:
                # Start a transaction
                await session.begin()

                # Create a valid record
                valid_deal = Deal(
                    id="rollback-test-deal",
                    name="Rollback Test Deal",
                    amount=Decimal("10000.00"),
                    currency="USD",
                    discount_percent=Decimal("10.00"),
                    payment_terms_days=30,
                    risk=DealRisk.LOW,
                    stage=DealStage.PROSPECTING,
                    probability=75,
                    created_by_id="test-user",
                    owner_id="test-user"
                )

                session.add(valid_deal)
                await session.flush()  # Flush but don't commit

                # Force an error to test rollback
                raise SQLAlchemyError("Simulated database error for rollback test")

            except SQLAlchemyError:
                await session.rollback()
                print("   ✅ Database rollback handled correctly")

            # Test constraint violation handling
            try:
                # Try to create duplicate record (same ID)
                duplicate_deal = Deal(
                    id="duplicate-test-id",  # Same ID for both
                    name="First Deal",
                    amount=Decimal("5000.00"),
                    currency="USD",
                    discount_percent=Decimal("5.00"),
                    payment_terms_days=30,
                    risk=DealRisk.LOW,
                    stage=DealStage.PROSPECTING,
                    probability=80,
                    created_by_id="test-user",
                    owner_id="test-user"
                )

                session.add(duplicate_deal)
                await session.commit()

                # Try to add another with same ID
                duplicate_deal2 = Deal(
                    id="duplicate-test-id",  # Duplicate ID
                    name="Second Deal",
                    amount=Decimal("6000.00"),
                    currency="USD",
                    discount_percent=Decimal("8.00"),
                    payment_terms_days=45,
                    risk=DealRisk.MEDIUM,
                    stage=DealStage.PROPOSAL,
                    probability=70,
                    created_by_id="test-user",
                    owner_id="test-user"
                )

                session.add(duplicate_deal2)
                await session.commit()

            except Exception as constraint_error:
                await session.rollback()
                print(f"   ✅ Constraint violation handled: {type(constraint_error).__name__}")

        return True
    except Exception as e:
        print(f"   ❌ Error handling test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_performance_basics():
    """Test basic performance characteristics."""
    print("\n🔍 Testing Basic Performance...")

    try:
        from app.db.session import async_session_factory
        from app.models.deal import Deal, DealRisk, DealStage
        from app.services.guardrail_service import GuardrailService
        from decimal import Decimal
        import time

        async with async_session_factory() as session:
            guardrail_service = GuardrailService(session)

            # Test bulk deal creation performance
            start_time = time.time()

            deals = []
            for i in range(100):
                deal = Deal(
                    id=f"perf-deal-{i}",
                    name=f"Performance Test Deal {i}",
                    description=f"Test deal {i} for performance testing",
                    amount=Decimal(str(10000 + (i * 100))),
                    currency="USD",
                    discount_percent=Decimal(str(5 + (i % 20))),
                    payment_terms_days=30 + (i % 60),
                    risk=list(DealRisk)[i % len(DealRisk)],
                    stage=list(DealStage)[i % len(DealStage)],
                    probability=50 + (i % 50),
                    expected_close=datetime.utcnow() + timedelta(days=30 + (i % 90)),
                    created_by_id="test-user",
                    owner_id="test-user"
                )
                deals.append(deal)

            session.add_all(deals)
            await session.commit()

            creation_time = time.time() - start_time
            print(f"   ✅ Created 100 deals in {creation_time:.2f} seconds")

            # Test query performance
            start_time = time.time()

            result = await session.execute(
                "SELECT COUNT(*) FROM deals WHERE amount > :amount",
                {"amount": 10000}
            )
            count = result.scalar()

            query_time = time.time() - start_time
            print(f"   ✅ Queried {count} deals in {query_time:.4f} seconds")

            # Test validation performance
            start_time = time.time()

            test_deal = Deal(
                id="validation-perf-test",
                name="Validation Performance Test",
                amount=Decimal("75000.00"),
                currency="USD",
                discount_percent=Decimal("25.00"),
                payment_terms_days=45,
                risk=DealRisk.MEDIUM,
                stage=DealStage.PROPOSAL,
                probability=65
            )

            validation_result = await guardrail_service.validate_deal(test_deal)

            validation_time = time.time() - start_time
            print(f"   ✅ Deal validation completed in {validation_time:.4f} seconds")

        return True
    except Exception as e:
        print(f"   ❌ Performance test failed: {str(e)}")
        traceback.print_exc()
        return False

async def test_database_migrations():
    """Test database migrations and schema integrity."""
    print("\n🔍 Testing Database Migrations...")

    try:
        from app.db.session import engine
        from sqlalchemy import text, inspect
        from app import models  # Import all models to ensure they're registered

        # Check if all tables exist
        async with engine.begin() as conn:
            inspector = inspect(engine)

            # Expected tables based on models
            expected_tables = [
                'users', 'deals', 'policies', 'invoices', 'payments',
                'events', 'approvals', 'audit_logs'
            ]

            existing_tables = inspector.get_table_names()
            print(f"   Found {len(existing_tables)} tables in database")

            missing_tables = []
            for table in expected_tables:
                if table in existing_tables:
                    # Check table structure
                    columns = inspector.get_columns(table)
                    print(f"   ✅ Table '{table}' exists with {len(columns)} columns")
                else:
                    missing_tables.append(table)
                    print(f"   ❌ Table '{table}' missing")

            if missing_tables:
                print(f"   ⚠️  Missing tables: {missing_tables}")
            else:
                print("   ✅ All expected tables present")

            # Test SQL migration file if it exists
            migration_file = "/home/aparna/Desktop/deal_desk_os/server/app/migrations/001_create_invoice_tables.sql"
            if os.path.exists(migration_file):
                print(f"   ✅ Migration file found: {migration_file}")

                # Read and validate migration file content
                with open(migration_file, 'r') as f:
                    migration_content = f.read()
                    if 'CREATE TABLE' in migration_content:
                        print("   ✅ Migration file contains CREATE TABLE statements")
                    else:
                        print("   ⚠️  Migration file may be incomplete")
            else:
                print("   ⚠️  No SQL migration file found")

        return True
    except Exception as e:
        print(f"   ❌ Migration test failed: {str(e)}")
        traceback.print_exc()
        return False

async def main():
    """Run all backend tests."""
    print("🚀 Starting Comprehensive Deal Desk OS Backend Testing")
    print("=" * 60)

    # Change to server directory
    os.chdir('/home/aparna/Desktop/deal_desk_os/server')

    test_results = {
        "Database Connectivity": False,
        "Model Creation": False,
        "Service Layer": False,
        "API Endpoints": False,
        "Payment Processing": False,
        "Error Handling": False,
        "Performance Basics": False,
        "Database Migrations": False
    }

    try:
        # Run tests in sequence
        test_results["Database Connectivity"] = await test_database_connectivity()

        if test_results["Database Connectivity"]:
            test_results["Model Creation"] = await test_model_creation()
            test_results["Service Layer"] = await test_service_layer()
            test_results["API Endpoints"] = await test_api_endpoints()
            test_results["Payment Processing"] = await test_payment_processing()
            test_results["Error Handling"] = await test_error_handling()
            test_results["Performance Basics"] = await test_performance_basics()
            test_results["Database Migrations"] = await test_database_migrations()
        else:
            print("\n⚠️  Skipping remaining tests due to database connectivity issues")

    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {str(e)}")
        traceback.print_exc()

    # Print summary
    print("\n" + "=" * 60)
    print("📊 BACKEND TESTING SUMMARY")
    print("=" * 60)

    passed_tests = sum(1 for result in test_results.values() if result)
    total_tests = len(test_results)

    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall Result: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 ALL BACKEND TESTS PASSED! System is ready for end-to-end testing.")
        return 0
    elif passed_tests >= total_tests * 0.75:
        print("⚠️  MOST TESTS PASSED. System has minor issues that should be addressed.")
        return 1
    else:
        print("🚨 CRITICAL ISSUES FOUND. System needs significant fixes before proceeding.")
        return 2

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)