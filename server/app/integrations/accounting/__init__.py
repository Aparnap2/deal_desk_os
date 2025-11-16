"""
Accounting Integration Package

Provides adapters for various accounting systems including QuickBooks,
NetSuite, SAP Business One, and other popular ERP systems.
"""

from .base import (
    AccountingAdapter,
    AccountingAdapterFactory,
    AccountingError,
    AccountingSystemType,
    CustomerDetails,
    CustomerResult,
    InvoiceRequest,
    InvoiceResult,
    InvoiceStatus,
    InvoiceStatusResult,
    LineItem,
    PaymentResult,
    TaxCalculation,
    TaxCalculationType,
)

# Import and register specific adapters
from .quickbooks_adapter import QuickBooksAdapter
from .netsuite_adapter import NetSuiteAdapter
from .sap_adapter import SAPAdapter

__all__ = [
    "AccountingAdapter",
    "AccountingAdapterFactory",
    "AccountingError",
    "AccountingSystemType",
    "CustomerDetails",
    "CustomerResult",
    "InvoiceRequest",
    "InvoiceResult",
    "InvoiceStatus",
    "InvoiceStatusResult",
    "LineItem",
    "PaymentResult",
    "TaxCalculation",
    "TaxCalculationType",
    "QuickBooksAdapter",
    "NetSuiteAdapter",
    "SAPAdapter",
]