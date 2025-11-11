"""
Basic Stripe adapter test to verify imports and initialization work.
"""

import pytest
from decimal import Decimal

from app.integrations.payment_gateways.stripe_adapter import StripeAdapter
from app.integrations.payment_gateways.base import (
    PaymentGatewayType,
    CustomerDetails,
    PaymentMethod,
    PaymentMethodType,
)


class TestStripeAdapterBasic:
    """Basic tests for Stripe adapter functionality."""

    @pytest.fixture
    def stripe_config(self):
        return {
            "api_key": "sk_test_123456789",
            "webhook_secret": "whsec_test_123456789",
            "publishable_key": "pk_test_123456789"
        }

    @pytest.fixture
    def stripe_adapter(self, stripe_config):
        return StripeAdapter(**stripe_config)

    def test_adapter_initialization(self, stripe_adapter, stripe_config):
        """Test that Stripe adapter initializes correctly."""
        assert stripe_adapter.gateway_type == PaymentGatewayType.STRIPE
        assert stripe_adapter.webhook_secret == stripe_config["webhook_secret"]
        assert stripe_adapter.publishable_key == stripe_config["publishable_key"]
        assert stripe_adapter.client is not None

    def test_get_supported_currencies(self, stripe_adapter):
        """Test that Stripe adapter returns supported currencies."""
        currencies = stripe_adapter.get_supported_currencies()
        assert "USD" in currencies
        assert "EUR" in currencies
        assert "GBP" in currencies
        assert len(currencies) > 20  # Stripe supports many currencies

    def test_get_supported_payment_methods(self, stripe_adapter):
        """Test that Stripe adapter returns supported payment methods."""
        methods = stripe_adapter.get_supported_payment_methods()
        assert PaymentMethodType.CARD in methods
        assert PaymentMethodType.BANK_ACCOUNT in methods
        assert PaymentMethodType.APPLE_PAY in methods
        assert PaymentMethodType.GOOGLE_PAY in methods

    def test_customer_details_creation(self, stripe_adapter):
        """Test customer details structure."""
        customer = CustomerDetails(
            email="test@example.com",
            name="John Doe",
            address={
                "line1": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94105",
                "country": "US"
            }
        )
        assert customer.email == "test@example.com"
        assert customer.name == "John Doe"
        assert customer.address["city"] == "San Francisco"

    def test_payment_method_creation(self, stripe_adapter):
        """Test payment method structure."""
        payment_method = PaymentMethod(
            type=PaymentMethodType.CARD,
            token="pm_stripe_123456789",
            last_four="4242",
            brand="visa",
            expiry_month=12,
            expiry_year=2025
        )
        assert payment_method.type == PaymentMethodType.CARD
        assert payment_method.token == "pm_stripe_123456789"
        assert payment_method.last_four == "4242"
        assert payment_method.brand == "visa"

    def test_stripe_status_mapping(self, stripe_adapter):
        """Test that Stripe status mapping works correctly."""
        # Test the private method through the public interface
        from app.integrations.payment_gateways.base import PaymentStatus

        # Test various status mappings
        status_map = stripe_adapter._map_stripe_status
        assert status_map("succeeded") == PaymentStatus.SUCCEEDED
        assert status_map("requires_payment_method") == PaymentStatus.PENDING
        assert status_map("requires_confirmation") == PaymentStatus.PENDING
        assert status_map("requires_action") == PaymentStatus.PENDING
        assert status_map("processing") == PaymentStatus.PENDING
        assert status_map("canceled") == PaymentStatus.CANCELED

    def test_fee_calculation(self, stripe_adapter):
        """Test Stripe fee calculation."""
        # Test $10.00
        fees_10 = stripe_adapter._calculate_stripe_fees(Decimal("10.00"))
        expected_10 = Decimal("10.00") * Decimal("0.029") + Decimal("0.30")
        assert fees_10 == expected_10.quantize(Decimal("0.01"))

        # Test $100.00
        fees_100 = stripe_adapter._calculate_stripe_fees(Decimal("100.00"))
        expected_100 = Decimal("100.00") * Decimal("0.029") + Decimal("0.30")
        assert fees_100 == expected_100.quantize(Decimal("0.01"))

        # Test $0.00
        fees_0 = stripe_adapter._calculate_stripe_fees(Decimal("0.00"))
        assert fees_0 == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_health_check_failures(self, stripe_adapter):
        """Test health check with invalid API key."""
        # Create adapter with invalid key to test error handling
        invalid_adapter = StripeAdapter(api_key="sk_invalid_key")

        # Health check should handle authentication error gracefully
        result = await invalid_adapter.health_check()
        assert result is False