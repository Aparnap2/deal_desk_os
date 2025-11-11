"""
Payment Gateway Base Classes and Interfaces

Defines the contract and base functionality for all payment gateway adapters
in the Deal Desk OS system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, List
from datetime import datetime


class PaymentGatewayType(str, Enum):
    """Supported payment gateway types."""
    STRIPE = "stripe"
    PAYPAL = "paypal"
    ADOBE = "adobe"  # Adobe Pay
    SQUARE = "square"
    SHOPIFY = "shopify"


class PaymentStatus(str, Enum):
    """Payment status enumeration."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethodType(str, Enum):
    """Payment method types."""
    CARD = "card"
    BANK_ACCOUNT = "bank_account"
    PAYPAL = "paypal"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    ACH = "ach"


@dataclass
class CustomerDetails:
    """Customer information for payment processing."""
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    company: Optional[str] = None
    tax_id: Optional[str] = None


@dataclass
class PaymentMethod:
    """Payment method details."""
    type: PaymentMethodType
    token: str
    last_four: Optional[str] = None
    brand: Optional[str] = None  # visa, mastercard, etc.
    expiry_month: Optional[int] = None
    expiry_year: Optional[int] = None
    fingerprint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PaymentResult:
    """Result of a payment operation."""
    success: bool
    transaction_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    gateway_type: PaymentGatewayType
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    fees: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None


@dataclass
class RefundResult:
    """Result of a refund operation."""
    success: bool
    refund_id: str
    payment_intent_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    gateway_type: PaymentGatewayType
    created_at: Optional[datetime] = None
    reason: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None
    fees: Optional[Decimal] = None


@dataclass
class PaymentStatusResult:
    """Result of payment status query."""
    success: bool
    transaction_id: str
    status: PaymentStatus
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    gateway_type: Optional[PaymentGatewayType] = None
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    refunds: Optional[List[Dict[str, Any]]] = None
    gateway_response: Optional[Dict[str, Any]] = None


class PaymentError(Exception):
    """Payment gateway specific errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        provider: Optional[str] = None,
        gateway_response: Optional[Dict[str, Any]] = None,
        transaction_id: Optional[str] = None
    ):
        super().__init__(message)
        self.error_message = message
        self.error_code = error_code
        self.provider = provider
        self.gateway_response = gateway_response
        self.transaction_id = transaction_id


class PaymentGateway(ABC):
    """Abstract base class for payment gateway adapters."""

    def __init__(self, **config):
        """Initialize the payment gateway with configuration."""
        self.config = config
        self.gateway_type = self._get_gateway_type()

    @abstractmethod
    def _get_gateway_type(self) -> PaymentGatewayType:
        """Return the gateway type identifier."""
        pass

    @abstractmethod
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
        Charge a payment method.

        Args:
            amount: Amount to charge
            currency: Currency code (USD, EUR, etc.)
            payment_method: Payment method details
            customer: Customer information
            description: Payment description
            metadata: Additional metadata
            idempotency_key: Idempotency key for preventing duplicates

        Returns:
            PaymentResult with charge details

        Raises:
            PaymentError: If charge fails
        """
        pass

    @abstractmethod
    async def refund(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> RefundResult:
        """
        Refund a payment.

        Args:
            payment_intent_id: Original payment transaction ID
            amount: Amount to refund (None for full refund)
            reason: Refund reason
            idempotency_key: Idempotency key

        Returns:
            RefundResult with refund details

        Raises:
            PaymentError: If refund fails
        """
        pass

    @abstractmethod
    async def get_payment_status(self, payment_intent_id: str) -> PaymentStatusResult:
        """
        Get the status of a payment.

        Args:
            payment_intent_id: Payment transaction ID

        Returns:
            PaymentStatusResult with current status

        Raises:
            PaymentError: If status query fails
        """
        pass

    @abstractmethod
    async def create_customer(self, customer: CustomerDetails) -> str:
        """
        Create a customer in the payment gateway.

        Args:
            customer: Customer details

        Returns:
            Customer ID in the gateway

        Raises:
            PaymentError: If customer creation fails
        """
        pass

    async def update_customer(self, customer_id: str, customer: CustomerDetails) -> str:
        """
        Update an existing customer.

        Args:
            customer_id: Gateway customer ID
            customer: Updated customer details

        Returns:
            Updated customer ID

        Raises:
            PaymentError: If update fails
        """
        raise NotImplementedError("Customer update not implemented for this gateway")

    async def create_payment_method(
        self,
        payment_method: PaymentMethod,
        customer_id: Optional[str] = None
    ) -> str:
        """
        Create a payment method in the gateway.

        Args:
            payment_method: Payment method details
            customer_id: Optional customer ID to attach to

        Returns:
            Payment method ID in the gateway

        Raises:
            PaymentError: If payment method creation fails
        """
        raise NotImplementedError("Payment method creation not implemented for this gateway")

    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Verify and parse webhook payload.

        Args:
            payload: Raw webhook payload
            signature: Webhook signature

        Returns:
            Parsed webhook event

        Raises:
            PaymentError: If webhook verification fails
        """
        raise NotImplementedError("Webhook verification not implemented for this gateway")

    async def health_check(self) -> bool:
        """
        Check if the payment gateway is healthy.

        Returns:
            True if gateway is responding correctly

        Raises:
            PaymentError: If health check fails
        """
        # Default implementation - override in subclasses
        return True

    def get_supported_currencies(self) -> List[str]:
        """
        Get list of supported currencies.

        Returns:
            List of supported currency codes
        """
        # Default to major currencies - override in subclasses
        return ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"]

    def get_supported_payment_methods(self) -> List[PaymentMethodType]:
        """
        Get list of supported payment method types.

        Returns:
            List of supported payment method types
        """
        # Default implementation - override in subclasses
        return [PaymentMethodType.CARD, PaymentMethodType.BANK_ACCOUNT]


class PaymentGatewayFactory:
    """Factory for creating payment gateway instances."""

    _gateways: Dict[PaymentGatewayType, type] = {}

    @classmethod
    def register_gateway(
        cls,
        gateway_type: PaymentGatewayType,
        gateway_class: type[PaymentGateway]
    ):
        """Register a payment gateway implementation."""
        cls._gateways[gateway_type] = gateway_class

    @classmethod
    def create_gateway(
        cls,
        gateway_type: PaymentGatewayType,
        **config
    ) -> PaymentGateway:
        """Create a payment gateway instance."""
        if gateway_type not in cls._gateways:
            raise ValueError(f"Unsupported gateway type: {gateway_type}")

        gateway_class = cls._gateways[gateway_type]
        return gateway_class(**config)

    @classmethod
    def get_supported_gateways(cls) -> List[PaymentGatewayType]:
        """Get list of registered gateway types."""
        return list(cls._gateways.keys())


# Register built-in gateways when they are imported
def _register_builtin_gateways():
    """Register built-in gateway implementations."""
    try:
        from .stripe_adapter import StripeAdapter
        PaymentGatewayFactory.register_gateway(PaymentGatewayType.STRIPE, StripeAdapter)
    except ImportError:
        pass

    try:
        from .paypal_adapter import PayPalAdapter
        PaymentGatewayFactory.register_gateway(PaymentGatewayType.PAYPAL, PayPalAdapter)
    except ImportError:
        pass


# Register gateways when module is imported
_register_builtin_gateways()