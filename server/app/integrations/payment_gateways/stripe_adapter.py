"""
Stripe Payment Gateway Adapter

Provides integration with Stripe payment processing platform
for the Deal Desk OS system.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from stripe import StripeClient, StripeError, CardError, APIError, AuthenticationError

from .base import (
    PaymentGateway,
    PaymentGatewayType,
    PaymentResult,
    RefundResult,
    PaymentStatusResult,
    PaymentError,
    CustomerDetails,
    PaymentMethod,
    PaymentMethodType,
    PaymentStatus,
)

logger = logging.getLogger(__name__)


class StripeAdapter(PaymentGateway):
    """Stripe payment gateway adapter."""

    def __init__(
        self,
        api_key: str,
        webhook_secret: Optional[str] = None,
        publishable_key: Optional[str] = None,
        **config
    ):
        """
        Initialize Stripe adapter.

        Args:
            api_key: Stripe secret API key
            webhook_secret: Stripe webhook secret for signature verification
            publishable_key: Stripe publishable key
            **config: Additional configuration
        """
        super().__init__(api_key=api_key, webhook_secret=webhook_secret, publishable_key=publishable_key, **config)
        self.client = StripeClient(api_key)
        self.webhook_secret = webhook_secret
        self.publishable_key = publishable_key

    def _get_gateway_type(self) -> PaymentGatewayType:
        """Return the gateway type identifier."""
        return PaymentGatewayType.STRIPE

    async def charge(
        self,
        amount: Decimal,
        currency: str,
        payment_method: PaymentMethod,
        customer: Optional[CustomerDetails] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> PaymentResult:
        """
        Charge a payment method using Stripe Payment Intents.

        Args:
            amount: Amount to charge
            currency: Currency code (USD, EUR, etc.)
            payment_method: Payment method details
            customer: Customer information
            description: Payment description
            metadata: Additional metadata
            idempotency_key: Idempotency key for preventing duplicates
            **kwargs: Additional parameters

        Returns:
            PaymentResult with charge details

        Raises:
            PaymentError: If charge fails
        """
        try:
            # Convert amount to cents (Stripe uses cents)
            amount_cents = int(amount * 100)

            # Create or get customer
            customer_id = None
            if customer:
                customer_id = await self._get_or_create_customer(customer)

            # Prepare payment intent data
            payment_intent_data = {
                "amount": amount_cents,
                "currency": currency.lower(),
                "payment_method": payment_method.token,
                "confirm": True,
                "automatic_payment_methods": {"enabled": True},
            }

            # Add optional parameters
            if customer_id:
                payment_intent_data["customer"] = customer_id
            if description:
                payment_intent_data["description"] = description
            if metadata:
                payment_intent_data["metadata"] = metadata
            if idempotency_key:
                payment_intent_data["idempotency_key"] = idempotency_key

            # Create payment intent using async client
            payment_intent = await self.client.v1.payment_intents.create_async(**payment_intent_data)

            # Determine payment status
            status = self._map_stripe_status(payment_intent.status)

            # Calculate fees (Stripe fees are typically 2.9% + $0.30 for US cards)
            fees = self._calculate_stripe_fees(amount)
            net_amount = amount - fees

            return PaymentResult(
                success=payment_intent.status in ["succeeded", "processing"],
                transaction_id=payment_intent.id,
                amount=amount,
                currency=currency.upper(),
                status=status,
                gateway_type=self.gateway_type,
                created_at=datetime.fromtimestamp(payment_intent.created, timezone.utc),
                processed_at=datetime.now(timezone.utc) if payment_intent.status == "succeeded" else None,
                failure_reason=None if payment_intent.status in ["succeeded", "processing"] else payment_intent.last_payment_error.get("message") if payment_intent.last_payment_error else None,
                gateway_response=dict(payment_intent),
                metadata=payment_intent.metadata or {},
                fees=fees,
                net_amount=net_amount
            )

        except CardError as e:
            logger.error(f"Stripe card error: {e}")
            raise PaymentError(
                message=e.user_message or "Card declined",
                error_code=e.code,
                provider="stripe",
                gateway_response={"error": str(e)},
                transaction_id=getattr(e, "payment_intent_id", None)
            )
        except StripeError as e:
            logger.error(f"Stripe API error: {e}")
            raise PaymentError(
                message=str(e),
                error_code="stripe_api_error",
                provider="stripe",
                gateway_response={"error": str(e)}
            )
        except Exception as e:
            logger.error(f"Unexpected error in Stripe charge: {e}")
            raise PaymentError(
                message=f"Unexpected error: {str(e)}",
                error_code="unexpected_error",
                provider="stripe"
            )

    async def refund(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> RefundResult:
        """
        Refund a payment using Stripe.

        Args:
            payment_intent_id: Original payment intent ID
            amount: Amount to refund (None for full refund)
            reason: Refund reason
            idempotency_key: Idempotency key
            **kwargs: Additional parameters

        Returns:
            RefundResult with refund details

        Raises:
            PaymentError: If refund fails
        """
        try:
            # Prepare refund data
            refund_data = {
                "payment_intent": payment_intent_id,
            }

            if amount:
                refund_data["amount"] = int(amount * 100)
            if reason:
                refund_data["reason"] = reason
            if idempotency_key:
                refund_data["idempotency_key"] = idempotency_key

            # Create refund using async client
            refund = await self.client.v1.refunds.create_async(**refund_data)

            # Convert amount back to Decimal
            refund_amount = Decimal(refund.amount) / 100

            return RefundResult(
                success=refund.status == "succeeded",
                refund_id=refund.id,
                payment_intent_id=payment_intent_id,
                amount=refund_amount,
                currency=refund.currency.upper(),
                status=self._map_stripe_status(refund.status),
                gateway_type=self.gateway_type,
                created_at=datetime.fromtimestamp(refund.created, timezone.utc),
                reason=refund.reason,
                gateway_response=dict(refund),
                fees=Decimal("0")  # Stripe doesn't charge fees for refunds
            )

        except StripeError as e:
            logger.error(f"Stripe refund error: {e}")
            raise PaymentError(
                message=str(e),
                error_code="stripe_refund_error",
                provider="stripe",
                gateway_response={"error": str(e)}
            )

    async def get_payment_status(self, payment_intent_id: str) -> PaymentStatusResult:
        """
        Get the status of a payment intent.

        Args:
            payment_intent_id: Payment intent ID

        Returns:
            PaymentStatusResult with current status

        Raises:
            PaymentError: If status query fails
        """
        try:
            # Retrieve payment intent using async client
            payment_intent = await self.client.v1.payment_intents.retrieve_async(payment_intent_id)

            # Get refunds
            refunds = []
            if payment_intent.charges:
                for charge in payment_intent.charges.data:
                    if charge.refunds:
                        for refund in charge.refunds.data:
                            refunds.append({
                                "id": refund.id,
                                "amount": Decimal(refund.amount) / 100,
                                "status": refund.status,
                                "created": datetime.fromtimestamp(refund.created, timezone.utc).isoformat(),
                                "reason": refund.reason
                            })

            # Convert amount
            amount = Decimal(payment_intent.amount) / 100 if payment_intent.amount else None

            return PaymentStatusResult(
                success=True,
                transaction_id=payment_intent.id,
                status=self._map_stripe_status(payment_intent.status),
                amount=amount,
                currency=payment_intent.currency.upper() if payment_intent.currency else None,
                gateway_type=self.gateway_type,
                created_at=datetime.fromtimestamp(payment_intent.created, timezone.utc),
                last_updated=datetime.fromtimestamp(payment_intent.last_response["date"] if payment_intent.last_response else payment_intent.created, timezone.utc),
                refunds=refunds,
                gateway_response=dict(payment_intent)
            )

        except StripeError as e:
            logger.error(f"Stripe status query error: {e}")
            raise PaymentError(
                message=str(e),
                error_code="stripe_status_error",
                provider="stripe",
                gateway_response={"error": str(e)}
            )

    async def create_customer(self, customer: CustomerDetails) -> str:
        """
        Create a customer in Stripe.

        Args:
            customer: Customer details

        Returns:
            Stripe customer ID

        Raises:
            PaymentError: If customer creation fails
        """
        try:
            # Prepare customer data
            customer_data = {
                "email": customer.email,
            }

            if customer.name:
                customer_data["name"] = customer.name
            if customer.phone:
                customer_data["phone"] = customer.phone
            if customer.address:
                customer_data["address"] = customer.address
            if customer.company:
                customer_data["business_name"] = customer.company

            # Create customer using async client
            stripe_customer = await self.client.v1.customers.create_async(**customer_data)
            return stripe_customer.id

        except StripeError as e:
            logger.error(f"Stripe customer creation error: {e}")
            raise PaymentError(
                message=str(e),
                error_code="stripe_customer_error",
                provider="stripe",
                gateway_response={"error": str(e)}
            )

    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Verify and parse Stripe webhook payload.

        Args:
            payload: Raw webhook payload
            signature: Stripe signature header

        Returns:
            Parsed webhook event

        Raises:
            PaymentError: If webhook verification fails
        """
        if not self.webhook_secret:
            raise PaymentError(
                message="Webhook secret not configured",
                error_code="webhook_secret_missing",
                provider="stripe"
            )

        try:
            event = stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
            return dict(event)

        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Stripe webhook signature verification failed: {e}")
            raise PaymentError(
                message="Invalid webhook signature",
                error_code="webhook_signature_invalid",
                provider="stripe",
                gateway_response={"error": str(e)}
            )
        except Exception as e:
            logger.error(f"Stripe webhook verification error: {e}")
            raise PaymentError(
                message=f"Webhook verification failed: {str(e)}",
                error_code="webhook_verification_error",
                provider="stripe"
            )

    async def health_check(self) -> bool:
        """
        Check if Stripe API is accessible.

        Returns:
            True if Stripe is responding correctly

        Raises:
            PaymentError: If health check fails
        """
        try:
            # Make a simple API call to check connectivity using async client
            await self.client.balance.retrieve_async()
            return True
        except AuthenticationError:
            # Authentication error means API is reachable but credentials are wrong
            logger.warning("Stripe health check: Authentication failed")
            return False
        except StripeError as e:
            logger.error(f"Stripe health check failed: {e}")
            raise PaymentError(
                message=f"Stripe health check failed: {str(e)}",
                error_code="stripe_health_check_error",
                provider="stripe"
            )

    def get_supported_currencies(self) -> list[str]:
        """Get list of supported currencies for Stripe."""
        return [
            "USD", "EUR", "GBP", "CAD", "AUD", "CHF", "SEK", "NOK", "DKK",
            "PLN", "CZK", "HUF", "RON", "BGN", "HRK", "RUB", "UAH",
            "MXN", "BRL", "ARS", "CLP", "COP", "PEN", "UYU",
            "JPY", "SGD", "HKD", "INR", "IDR", "MYR", "PHP", "THB", "VND"
        ]

    def get_supported_payment_methods(self) -> list[PaymentMethodType]:
        """Get list of supported payment method types for Stripe."""
        return [
            PaymentMethodType.CARD,
            PaymentMethodType.BANK_ACCOUNT,
            PaymentMethodType.APPLE_PAY,
            PaymentMethodType.GOOGLE_PAY,
            PaymentMethodType.ACH,
        ]

    async def _get_or_create_customer(self, customer: CustomerDetails) -> Optional[str]:
        """Get existing customer or create new one."""
        try:
            # Try to find existing customer by email using async client
            existing_customers = await self.client.v1.customers.list_async(email=customer.email, limit=1)
            if existing_customers.data:
                return existing_customers.data[0].id
        except StripeError:
            # Continue to create new customer if search fails
            pass

        # Create new customer
        return await self.create_customer(customer)

    def _map_stripe_status(self, stripe_status: str) -> PaymentStatus:
        """Map Stripe status to our PaymentStatus enum."""
        status_mapping = {
            "requires_payment_method": PaymentStatus.PENDING,
            "requires_confirmation": PaymentStatus.PENDING,
            "requires_action": PaymentStatus.PENDING,
            "processing": PaymentStatus.PENDING,
            "succeeded": PaymentStatus.SUCCEEDED,
            "canceled": PaymentStatus.CANCELED,
            "requires_capture": PaymentStatus.PENDING,
        }
        return status_mapping.get(stripe_status, PaymentStatus.PENDING)

    def _calculate_stripe_fees(self, amount: Decimal) -> Decimal:
        """
        Calculate Stripe fees for a given amount.

        Default US card processing fees: 2.9% + $0.30
        This can be overridden based on actual Stripe pricing.
        """
        if amount <= 0:
            return Decimal("0")

        # Default pricing for US cards (can be configured)
        percentage_fee = Decimal("0.029")  # 2.9%
        fixed_fee = Decimal("0.30")  # $0.30

        fees = (amount * percentage_fee) + fixed_fee
        return fees.quantize(Decimal("0.01"))