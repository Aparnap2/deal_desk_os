"""
Shared test configuration and fixtures for Deal Desk OS testing suite.
"""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Generator, Optional
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.config import get_settings
from app.models.deal import Deal, DealRisk, DealStage, GuardrailStatus
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentStatus
from app.models.policy import Policy, PolicyStatus, PolicyType
from app.models.user import User, UserRole


# Test database configuration
TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_deal_desk_os"

# Create async test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)

TestSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_db_session() -> AsyncSession:
    """Create async database session for testing."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def test_client(async_db_session) -> Generator[TestClient, None, None]:
    """Create test client with database dependency override."""
    from app.api.dependencies.database import get_db

    app.dependency_overrides[get_db] = lambda: async_db_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.app_name = "Deal Desk OS Test"
    settings.environment = "test"
    settings.secret_key = "test-secret-key-for-testing-only"
    settings.access_token_expire_minutes = 60
    settings.database_url = TEST_DATABASE_URL
    settings.redis_url = "redis://localhost:6379/1"
    settings.allowed_origins = []

    # n8n settings
    settings.n8n_enabled = True
    settings.n8n_webhook_url = "https://test-n8n.example.com/webhook"
    settings.n8n_api_key = "test_n8n_api_key"
    settings.n8n_signature_secret = "test_n8n_signature_secret"
    settings.n8n_timeout_seconds = 30
    settings.n8n_retry_attempts = 3
    settings.n8n_retry_delay_seconds = 5

    return settings


@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        id="test-user-123",
        email="test@example.com",
        full_name="Test User",
        hashed_password="hashed_password",
        roles=[UserRole.REVOPS_USER],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def test_admin_user():
    """Create a test admin user."""
    return User(
        id="admin-user-123",
        email="admin@example.com",
        full_name="Test Admin",
        hashed_password="hashed_admin_password",
        roles=[UserRole.REVOPS_ADMIN],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def test_deal():
    """Create a test deal."""
    return Deal(
        id="deal-123",
        name="Test Deal",
        description="A test deal for unit testing",
        amount=Decimal("10000.00"),
        currency="USD",
        discount_percent=Decimal("15.00"),
        payment_terms_days=30,
        risk=DealRisk.LOW,
        probability=75,
        stage=DealStage.PROSPECTING,
        expected_close=datetime.utcnow() + timedelta(days=30),
        created_by_id="test-user-123",
        owner_id="test-user-123",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def test_policy():
    """Create a test policy."""
    return Policy(
        id="policy-123",
        name="Test Pricing Policy",
        description="Test policy for pricing guardrails",
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
        priority=10,
        status=PolicyStatus.ACTIVE,
        created_by_id="admin-user-123",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def test_invoice():
    """Create a test invoice."""
    return Invoice(
        id="invoice-123",
        deal_id="deal-123",
        invoice_number="INV-001",
        amount=Decimal("10000.00"),
        currency="USD",
        status=InvoiceStatus.DRAFT,
        invoice_type=InvoiceType.STANDARD,
        due_date=datetime.utcnow() + timedelta(days=30),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def test_payment():
    """Create a test payment."""
    return Payment(
        id="payment-123",
        deal_id="deal-123",
        invoice_id="invoice-123",
        amount=Decimal("10000.00"),
        currency="USD",
        status=PaymentStatus.PENDING,
        gateway_transaction_id="stripe_payment_123",
        gateway_provider="stripe",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_stripe_adapter():
    """Mock Stripe adapter for testing."""
    adapter = Mock()
    adapter.gateway_type = "stripe"
    adapter.create_payment_intent = AsyncMock(return_value={
        "id": "pi_test_123",
        "status": "requires_payment_method",
        "client_secret": "pi_test_123_secret_test",
    })
    adapter.confirm_payment = AsyncMock(return_value={
        "status": "succeeded",
        "id": "pi_test_123",
    })
    adapter.refund_payment = AsyncMock(return_value={
        "status": "succeeded",
        "id": "re_test_123",
    })
    adapter.health_check = AsyncMock(return_value=True)
    return adapter


@pytest.fixture
def mock_n8n_client():
    """Mock n8n client for testing."""
    client = Mock()
    client.trigger_workflow = AsyncMock(return_value={
        "workflow_id": "workflow_123",
        "execution_id": "execution_123",
        "status": "success",
    })
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_quote_to_cash_workflow_data():
    """Sample data for quote-to-cash workflow testing."""
    return {
        "deal": {
            "id": "deal-qtc-123",
            "name": "Enterprise Customer Deal",
            "amount": "50000.00",
            "currency": "USD",
            "stage": "proposal",
            "risk": "medium",
            "discount_percent": "15.0",
            "payment_terms_days": 45,
        },
        "customer": {
            "id": "customer-123",
            "name": "Acme Corporation",
            "email": "billing@acme.com",
            "billing_address": {
                "line1": "123 Business St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94105",
                "country": "US",
            },
        },
        "quote": {
            "id": "quote-123",
            "number": "Q-2024-001",
            "valid_until": datetime.utcnow() + timedelta(days=30),
            "terms": "Net 45",
        },
        "workflow": {
            "type": "quote_to_cash",
            "steps": [
                "validate_deal",
                "create_invoice",
                "send_for_signature",
                "collect_payment",
                "activate_subscription",
            ],
        },
    }


@pytest.fixture
def performance_test_data():
    """Data for performance testing scenarios."""
    return {
        "concurrent_deals": [
            {
                "id": f"deal-perf-{i}",
                "name": f"Performance Test Deal {i}",
                "amount": str(10000 + (i * 1000)),
                "currency": "USD",
                "risk": "low" if i % 3 == 0 else "medium",
                "discount_percent": str(5 + (i % 20)),
                "payment_terms_days": 30 + (i % 60),
            }
            for i in range(100)
        ],
        "load_test_config": {
            "concurrent_users": 50,
            "duration_seconds": 300,
            "ramp_up_seconds": 30,
            "think_time_seconds": 2,
        },
    }


@pytest.fixture
def test_headers():
    """Common headers for API testing."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@pytest.fixture
def auth_headers(test_user):
    """Authorization headers for API testing."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {test_user.id}",
    }


# Test data generators
@pytest.fixture
def generate_test_deal():
    """Factory function to generate test deals with variations."""
    def _create_deal(**overrides):
        defaults = {
            "id": "test-deal-123",
            "name": "Test Deal",
            "amount": Decimal("10000.00"),
            "currency": "USD",
            "discount_percent": Decimal("15.00"),
            "payment_terms_days": 30,
            "risk": DealRisk.LOW,
            "stage": DealStage.PROSPECTING,
            "probability": 75,
        }
        defaults.update(overrides)
        return Deal(**defaults)
    return _create_deal


@pytest.fixture
def generate_test_policy():
    """Factory function to generate test policies with variations."""
    def _create_policy(policy_type=PolicyType.PRICING, **overrides):
        defaults = {
            "id": "test-policy-123",
            "name": "Test Policy",
            "description": "Test policy description",
            "policy_type": policy_type,
            "configuration": {},
            "priority": 10,
            "status": PolicyStatus.ACTIVE,
        }

        if policy_type == PolicyType.PRICING:
            defaults["configuration"] = {
                "discount_guardrails": {
                    "default_max_discount_percent": 25,
                    "risk_overrides": {"low": 30, "medium": 20, "high": 10},
                },
                "price_floor": {"currency": "USD", "min_amount": 5000},
            }
        elif policy_type == PolicyType.SLA:
            defaults["configuration"] = {
                "touch_rate_target": 0.95,
                "response_time_threshold": 24,
                "escalation_rules": {"level1_after": 48, "level2_after": 72},
            }

        defaults.update(overrides)
        return Policy(**defaults)
    return _create_policy


# Performance testing fixtures
@pytest.fixture
async def benchmark_timer():
    """Context manager for benchmarking execution time."""
    import time

    class BenchmarkTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.duration = None

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.end_time = time.perf_counter()
            self.duration = self.end_time - self.start_time

        @property
        def elapsed_ms(self) -> float:
            return self.duration * 1000 if self.duration else 0

    return BenchmarkTimer


@pytest.fixture
def memory_profiler():
    """Context manager for memory profiling."""
    import psutil
    import os

    class MemoryProfiler:
        def __init__(self):
            self.process = psutil.Process(os.getpid())
            self.start_memory = None
            self.end_memory = None
            self.peak_memory = None

        def __enter__(self):
            self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = self.start_memory
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = max(self.peak_memory, self.end_memory)

        @property
        def memory_increase_mb(self) -> float:
            return self.end_memory - self.start_memory if self.end_memory and self.start_memory else 0

    return MemoryProfiler


# Database seeding fixtures
@pytest_asyncio.fixture
async def seed_test_data(async_db_session):
    """Seed database with test data for integration testing."""
    # Create test users
    users = [
        User(
            id=f"user-{i}",
            email=f"user{i}@example.com",
            full_name=f"Test User {i}",
            hashed_password="hashed_password",
            roles=[UserRole.REVOPS_USER] if i > 0 else [UserRole.REVOPS_ADMIN],
            is_active=True,
        )
        for i in range(10)
    ]

    # Create test deals
    deals = [
        Deal(
            id=f"deal-{i}",
            name=f"Test Deal {i}",
            amount=Decimal(str(10000 + (i * 5000))),
            currency="USD",
            discount_percent=Decimal(str(10 + (i % 20))),
            payment_terms_days=30 + (i % 60),
            risk=list(DealRisk)[i % len(DealRisk)],
            stage=list(DealStage)[i % len(DealStage)],
            probability=50 + (i % 50),
            owner_id=f"user-{i % 10}",
            created_by_id="user-0",
        )
        for i in range(50)
    ]

    # Add to session
    async with async_db_session:
        async_db_session.add_all(users)
        async_db_session.add_all(deals)
        await async_db_session.commit()

        return {"users": users, "deals": deals}