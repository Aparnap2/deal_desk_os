"""
Payment Gateway Integration Tests

Test suite for payment gateway adapters (Stripe, PayPal, etc.)
following TDD principles for Deal Desk OS integration requirements.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, Mock, patch

from app.integrations.payment_gateways.base import (
    PaymentGateway,
    PaymentResult,
    PaymentError,
    RefundResult,
    CustomerDetails,
    PaymentMethod,
)
from app.integrations.payment_gateways.stripe_adapter import StripeAdapter
from app.integrations.payment_gateways.paypal_adapter import PayPalAdapter
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate


class TestPaymentGatewayContract:
    """Contract tests for all payment gateway implementations."""

    @pytest.mark.asyncio
    async def test_payment_gateway_interface_compliance(self):
        """Test that all payment gateways implement the required interface."""
        # This test ensures any new gateway implements the contract
        required_methods = ['charge', 'refund', 'get_payment_status', 'create_customer']

        for gateway_class in [StripeAdapter, PayPalAdapter]:
            gateway = gateway_class(api_key="test_key")

            for method_name in required_methods:
                assert hasattr(gateway, method_name), f"{gateway_class.__name__} missing {method_name}"
                assert callable(getattr(gateway, method_name)), f"{gateway_class.__name__}.{method_name} not callable"


class TestStripeAdapter:
    """Test Stripe payment gateway adapter."""

    @pytest.fixture
    def stripe_config(self):
        return {
            "api_key": "sk_test_123",
            "webhook_secret": "whsec_test_123",
            "publishable_key": "pk_test_123"
        }

    @pytest.fixture
    def stripe_adapter(self, stripe_config):
        return StripeAdapter(**stripe_config)

    @pytest.fixture
    def sample_customer_details(self):
        return CustomerDetails(
            email="customer@example.com",
            name="John Doe",
            address={
                "line1": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94105",
                "country": "US"
            }
        )

    @pytest.fixture
    def sample_payment_method(self):
        return PaymentMethod(
            type="card",
            token="pm_stripe_123",
            last_four="4242",
            brand="visa",
            expiry_month=12,
            expiry_year=2025
        )

    @pytest.mark.asyncio
    async def test_charge_success(self, stripe_adapter, sample_customer_details, sample_payment_method):
        """Test successful payment charge."""
        amount = Decimal("100.00")
        currency = "USD"
        description = "Test payment"

        # Mock Stripe API response
        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_test_123"
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.amount = int(amount * 100)  # Stripe uses cents
        mock_payment_intent.currency = currency.lower()
        mock_payment_intent.description = description
        mock_payment_intent.created = int(datetime.now(timezone.utc).timestamp())

        with patch('stripe.PaymentIntent.create') as mock_create:
            mock_create.return_value = mock_payment_intent

            result = await stripe_adapter.charge(
                amount=amount,
                currency=currency,
                payment_method=sample_payment_method,
                customer=sample_customer_details,
                description=description,
                metadata={"deal_id": "deal_123"}
            )

            assert isinstance(result, PaymentResult)
            assert result.success is True
            assert result.transaction_id == "pi_test_123"
            assert result.amount == amount
            assert result.currency == currency
            assert result.status == "succeeded"
            assert result.metadata["deal_id"] == "deal_123"

            # Verify Stripe was called correctly
            mock_create.assert_called_once_with(
                amount=int(amount * 100),
                currency=currency.lower(),
                payment_method="pm_stripe_123",
                customer=None,  # Will be created if not exists
                description=description,
                metadata={"deal_id": "deal_123"},
                confirm=True,
                automatic_payment_methods={"enabled": True}
            )

    @pytest.mark.asyncio
    async def test_charge_failure_insufficient_funds(self, stripe_adapter, sample_customer_details, sample_payment_method):
        """Test payment charge with insufficient funds."""
        amount = Decimal("100.00")
        currency = "USD"

        # Mock Stripe API error
        from stripe.error import CardError
        mock_create = AsyncMock(side_effect=CardError(
            message="Insufficient funds",
            param="amount",
            code="card_declined",
            json_body={"error": {"code": "insufficient_funds"}}
        ))

        with patch('stripe.PaymentIntent.create', mock_create):
            with pytest.raises(PaymentError) as exc_info:
                await stripe_adapter.charge(
                    amount=amount,
                    currency=currency,
                    payment_method=sample_payment_method,
                    customer=sample_customer_details
                )

            assert exc_info.value.error_code == "insufficient_funds"
            assert exc_info.value.error_message == "Insufficient funds"
            assert exc_info.value.provider == "stripe"

    @pytest.mark.asyncio
    async def test_charge_with_idempotency(self, stripe_adapter, sample_customer_details, sample_payment_method):
        """Test idempotent payment charge."""
        amount = Decimal("100.00")
        currency = "USD"
        idempotency_key = "idemp_123456"

        mock_payment_intent = Mock()
        mock_payment_intent.id = "pi_test_123"
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.amount = int(amount * 100)
        mock_payment_intent.currency = currency.lower()

        with patch('stripe.PaymentIntent.create') as mock_create:
            mock_create.return_value = mock_payment_intent

            await stripe_adapter.charge(
                amount=amount,
                currency=currency,
                payment_method=sample_payment_method,
                customer=sample_customer_details,
                idempotency_key=idempotency_key
            )

            # Verify idempotency key was passed
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs['idempotency_key'] == idempotency_key

    @pytest.mark.asyncio
    async def test_refund_success(self, stripe_adapter):
        """Test successful payment refund."""
        payment_intent_id = "pi_test_123"
        amount = Decimal("50.00")

        mock_refund = Mock()
        mock_refund.id = "re_test_123"
        mock_refund.amount = int(amount * 100)
        mock_refund.currency = "usd"
        mock_refund.status = "succeeded"
        mock_refund.payment_intent = payment_intent_id

        with patch('stripe.Refund.create') as mock_create:
            mock_create.return_value = mock_refund

            result = await stripe_adapter.refund(
                payment_intent_id=payment_intent_id,
                amount=amount,
                reason="requested_by_customer"
            )

            assert isinstance(result, RefundResult)
            assert result.success is True
            assert result.refund_id == "re_test_123"
            assert result.amount == amount
            assert result.payment_intent_id == payment_intent_id
            assert result.status == "succeeded"

            mock_create.assert_called_once_with(
                payment_intent=payment_intent_id,
                amount=int(amount * 100),
                reason="requested_by_customer"
            )

    @pytest.mark.asyncio
    async def test_get_payment_status(self, stripe_adapter):
        """Test getting payment status."""
        payment_intent_id = "pi_test_123"

        mock_payment_intent = Mock()
        mock_payment_intent.id = payment_intent_id
        mock_payment_intent.status = "succeeded"
        mock_payment_intent.amount = 10000  # cents
        mock_payment_intent.currency = "usd"

        with patch('stripe.PaymentIntent.retrieve') as mock_retrieve:
            mock_retrieve.return_value = mock_payment_intent

            result = await stripe_adapter.get_payment_status(payment_intent_id)

            assert result.success is True
            assert result.transaction_id == payment_intent_id
            assert result.status == "succeeded"
            assert result.amount == Decimal("100.00")
            assert result.currency == "USD"

    @pytest.mark.asyncio
    async def test_create_customer(self, stripe_adapter, sample_customer_details):
        """Test customer creation."""
        mock_customer = Mock()
        mock_customer.id = "cus_test_123"
        mock_customer.email = sample_customer_details.email
        mock_customer.name = sample_customer_details.name

        with patch('stripe.Customer.create') as mock_create:
            mock_create.return_value = mock_customer

            customer_id = await stripe_adapter.create_customer(sample_customer_details)

            assert customer_id == "cus_test_123"
            mock_create.assert_called_once_with(
                email=sample_customer_details.email,
                name=sample_customer_details.name,
                address=sample_customer_details.address
            )

    @pytest.mark.asyncio
    async def test_webhook_signature_validation(self, stripe_adapter):
        """Test webhook signature validation."""
        payload = b'{"id": "evt_test_123", "type": "payment_intent.succeeded"}'
        signature = "t=1234567890,v1=test_signature"

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = Mock()
            mock_event.type = "payment_intent.succeeded"
            mock_event.data.object = Mock()
            mock_event.data.object.id = "pi_test_123"
            mock_construct.return_value = mock_event

            event = await stripe_adapter.verify_webhook(payload, signature)

            assert event.type == "payment_intent.succeeded"
            assert event.data.object.id == "pi_test_123"
            mock_construct.assert_called_once_with(
                payload,
                signature,
                stripe_adapter.webhook_secret
            )

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, stripe_adapter):
        """Test webhook signature validation failure."""
        payload = b'{"id": "evt_test_123"}'
        invalid_signature = "invalid_signature"

        with patch('stripe.Webhook.construct_event') as mock_construct:
            from stripe.error import SignatureVerificationError
            mock_construct.side_effect = SignatureVerificationError(
                "Invalid signature",
                "t=1234567890,v1=invalid_signature"
            )

            with pytest.raises(PaymentError) as exc_info:
                await stripe_adapter.verify_webhook(payload, invalid_signature)

            assert exc_info.value.error_code == "webhook_signature_invalid"
            assert "Invalid signature" in exc_info.value.error_message


class TestPayPalAdapter:
    """Test PayPal payment gateway adapter."""

    @pytest.fixture
    def paypal_config(self):
        return {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "sandbox": True,
            "webhook_id": "test_webhook_id"
        }

    @pytest.fixture
    def paypal_adapter(self, paypal_config):
        return PayPalAdapter(**paypal_config)

    @pytest.mark.asyncio
    async def test_charge_success(self, paypal_adapter):
        """Test successful PayPal payment charge."""
        amount = Decimal("100.00")
        currency = "USD"
        payment_token = "PAY-12345"

        mock_order = Mock()
        mock_order.id = "ORDER-12345"
        mock_order.status = "APPROVED"
        mock_order.purchase_units = [
            Mock(
                amount=Mock(
                    currency_code=currency,
                    value=str(amount)
                )
            )
        ]

        mock_capture = Mock()
        mock_capture.id = "CAPTURE-12345"
        mock_capture.status = "COMPLETED"
        mock_capture.amount = Mock(
            currency_code=currency,
            value=str(amount)
        )

        with patch('aiohttp.ClientSession.post') as mock_post:
            # Mock order approval
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={
                "id": "ORDER-12345",
                "status": "APPROVED"
            })
            mock_post.return_value.__aenter__.return_value.status = 200

            # Mock payment capture
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={
                "id": "CAPTURE-12345",
                "status": "COMPLETED",
                "amount": {"currency_code": currency, "value": str(amount)}
            })

            result = await paypal_adapter.charge(
                amount=amount,
                currency=currency,
                payment_method=PaymentMethod(type="paypal", token=payment_token),
                description="Test payment"
            )

            assert isinstance(result, PaymentResult)
            assert result.success is True
            assert result.transaction_id == "CAPTURE-12345"
            assert result.amount == amount
            assert result.currency == currency
            assert result.status == "completed"


class TestPaymentGatewayIntegration:
    """Integration tests for payment gateways with existing payment system."""

    @pytest.mark.asyncio
    async def test_payment_service_with_stripe_integration(self):
        """Test integration between payment service and Stripe adapter."""
        # This will test the full integration with the existing PaymentService
        # We'll implement this when creating the actual adapter integration

        pass

    @pytest.mark.asyncio
    async def test_idempotency_across_gateways(self):
        """Test idempotency works correctly across different gateway implementations."""
        # Test that the same idempotency key prevents duplicate charges
        # even when using different underlying gateway implementations

        pass

    @pytest.mark.asyncio
    async def test_gateway_failover_logic(self):
        """Test failover logic when primary gateway fails."""
        # Test automatic failover to backup gateway
        # This will be important for SLA requirements

        pass

    @pytest.mark.asyncio
    async def test_multi_currency_support(self):
        """Test multi-currency payment processing."""
        # Test EUR, GBP, etc. payments work correctly

        pass

    @pytest.mark.asyncio
    async def test_load_testing_payment_gateways(self):
        """Load test payment gateway performance."""
        # Test concurrent payment processing for 50-200 deals
        # This addresses the SLA requirements

        pass


class TestPaymentGatewayErrorHandling:
    """Test error handling and retry logic for payment gateways."""

    @pytest.mark.asyncio
    async def test_network_timeout_retry(self):
        """Test retry logic on network timeouts."""

        pass

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test handling of gateway rate limits."""

        pass

    @pytest.mark.asyncio
    async def test_partial_failures(self):
        """Test handling of partial payment failures."""

        pass