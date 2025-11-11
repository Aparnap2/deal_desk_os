"""
Payment gateway integration modules

Provides adapters for various payment processing platforms
with consistent interface and error handling.
"""

from .base import (
    PaymentGateway,
    PaymentGatewayFactory,
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

__all__ = [
    "PaymentGateway",
    "PaymentGatewayFactory",
    "PaymentGatewayType",
    "PaymentResult",
    "RefundResult",
    "PaymentStatusResult",
    "PaymentError",
    "CustomerDetails",
    "PaymentMethod",
    "PaymentMethodType",
    "PaymentStatus",
]