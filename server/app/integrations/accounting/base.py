"""
Accounting System Base Classes and Interfaces

Defines the contract and base functionality for all accounting system adapters
in the Deal Desk OS system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, List
from datetime import datetime


class AccountingSystemType(str, Enum):
    """Supported accounting system types."""
    QUICKBOOKS = "quickbooks"
    NETSUITE = "netsuite"
    SAP = "sap"
    XERO = "xero"
    FRESHBOOKS = "freshbooks"
    WAVE = "wave"


class InvoiceStatus(str, Enum):
    """Invoice status enumeration."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    PAID = "paid"
    VOID = "void"
    PARTIALLY_PAID = "partially_paid"


class TaxCalculationType(str, Enum):
    """Tax calculation methods."""
    AUTO = "auto"  # Automatic calculation
    MANUAL = "manual"  # Manual entry
    EXEMPT = "exempt"  # Tax exempt


class CustomerStatus(str, Enum):
    """Customer status in accounting system."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


@dataclass
class CustomerDetails:
    """Customer information for accounting system."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    company: Optional[str] = None
    tax_id: Optional[str] = None
    currency: str = "USD"
    payment_terms_days: int = 30
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class LineItem:
    """Invoice line item details."""
    description: str
    quantity: Decimal
    unit_price: Decimal
    sku: Optional[str] = None
    discount_percent: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    tax_type: Optional[str] = None
    erp_item_id: Optional[str] = None
    erp_account_id: Optional[str] = None
    erp_tax_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @property
    def line_total(self) -> Decimal:
        """Calculate line total before tax."""
        subtotal = self.quantity * self.unit_price
        if self.discount_percent:
            discount_amount = subtotal * (self.discount_percent / Decimal("100"))
            subtotal -= discount_amount
        return subtotal

    @property
    def line_total_with_tax(self) -> Decimal:
        """Calculate line total including tax."""
        return self.line_total + self.tax_amount


@dataclass
class TaxCalculation:
    """Tax calculation details."""
    tax_name: str
    tax_rate: Decimal  # Percentage rate
    taxable_amount: Decimal
    tax_amount: Decimal
    tax_jurisdiction: Optional[str] = None
    tax_type: TaxCalculationType = TaxCalculationType.AUTO
    erp_tax_code: Optional[str] = None
    erp_tax_account: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class InvoiceRequest:
    """Request for creating an invoice in accounting system."""
    invoice_number: str
    customer: CustomerDetails
    line_items: List[LineItem]
    tax_calculations: Optional[List[TaxCalculation]] = None
    invoice_date: datetime = None
    due_date: datetime = None
    description: Optional[str] = None
    currency: str = "USD"
    payment_terms_days: int = 30
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.invoice_date is None:
            self.invoice_date = datetime.utcnow()
        if self.due_date is None:
            from datetime import timedelta
            self.due_date = self.invoice_date + timedelta(days=self.payment_terms_days)

    @property
    def subtotal(self) -> Decimal:
        """Calculate invoice subtotal."""
        return sum(item.line_total for item in self.line_items)

    @property
    def tax_amount(self) -> Decimal:
        """Calculate total tax amount."""
        if self.tax_calculations:
            return sum(tax.tax_amount for tax in self.tax_calculations)
        return sum(item.tax_amount for item in self.line_items)

    @property
    def total_amount(self) -> Decimal:
        """Calculate total amount including tax."""
        return self.subtotal + self.tax_amount


@dataclass
class CustomerResult:
    """Result of customer creation/update operation."""
    success: bool
    customer_id: Optional[str] = None
    customer_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


@dataclass
class InvoiceResult:
    """Result of invoice creation/update operation."""
    success: bool
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_url: Optional[str] = None
    customer_id: Optional[str] = None
    status: Optional[InvoiceStatus] = None
    created_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    error_message: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None
    invoice_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class InvoiceStatusResult:
    """Result of invoice status query."""
    success: bool
    invoice_id: str
    status: Optional[InvoiceStatus] = None
    amount: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    customer_id: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None


@dataclass
class PaymentResult:
    """Result of payment application operation."""
    success: bool
    payment_id: Optional[str] = None
    invoice_id: str
    amount: Decimal
    applied_at: Optional[datetime] = None
    remaining_balance: Optional[Decimal] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None


class AccountingError(Exception):
    """Accounting system specific errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        provider: Optional[str] = None,
        gateway_response: Optional[Dict[str, Any]] = None,
        invoice_id: Optional[str] = None,
        customer_id: Optional[str] = None
    ):
        super().__init__(message)
        self.error_message = message
        self.error_code = error_code
        self.provider = provider
        self.gateway_response = gateway_response
        self.invoice_id = invoice_id
        self.customer_id = customer_id


class AccountingAdapter(ABC):
    """Abstract base class for accounting system adapters."""

    def __init__(self, **config):
        """Initialize the accounting adapter with configuration."""
        self.config = config
        self.system_type = self._get_system_type()

    @abstractmethod
    def _get_system_type(self) -> AccountingSystemType:
        """Return the accounting system type identifier."""
        pass

    @abstractmethod
    async def create_or_update_customer(
        self,
        customer: CustomerDetails,
        customer_id: Optional[str] = None
    ) -> CustomerResult:
        """
        Create or update a customer in the accounting system.

        Args:
            customer: Customer details
            customer_id: Existing customer ID (for updates)

        Returns:
            CustomerResult with operation details

        Raises:
            AccountingError: If operation fails
        """
        pass

    @abstractmethod
    async def create_invoice(
        self,
        invoice_request: InvoiceRequest,
        customer_id: Optional[str] = None,
        draft: bool = True
    ) -> InvoiceResult:
        """
        Create an invoice in the accounting system.

        Args:
            invoice_request: Invoice details and line items
            customer_id: Customer ID in accounting system
            draft: Create as draft if True, post immediately if False

        Returns:
            InvoiceResult with operation details

        Raises:
            AccountingError: If invoice creation fails
        """
        pass

    @abstractmethod
    async def update_invoice(
        self,
        invoice_id: str,
        invoice_request: InvoiceRequest
    ) -> InvoiceResult:
        """
        Update an existing invoice in the accounting system.

        Args:
            invoice_id: Existing invoice ID
            invoice_request: Updated invoice details

        Returns:
            InvoiceResult with operation details

        Raises:
            AccountingError: If invoice update fails
        """
        pass

    @abstractmethod
    async def post_invoice(
        self,
        invoice_id: str,
        send_to_customer: bool = False
    ) -> InvoiceResult:
        """
        Post/submit a draft invoice to make it official.

        Args:
            invoice_id: Invoice ID to post
            send_to_customer: Whether to send to customer immediately

        Returns:
            InvoiceResult with posting details

        Raises:
            AccountingError: If posting fails
        """
        pass

    @abstractmethod
    async def get_invoice_status(self, invoice_id: str) -> InvoiceStatusResult:
        """
        Get the status of an invoice.

        Args:
            invoice_id: Invoice ID to query

        Returns:
            InvoiceStatusResult with current status

        Raises:
            AccountingError: If status query fails
        """
        pass

    @abstractmethod
    async def void_invoice(
        self,
        invoice_id: str,
        reason: Optional[str] = None
    ) -> InvoiceResult:
        """
        Void an invoice in the accounting system.

        Args:
            invoice_id: Invoice ID to void
            reason: Reason for voiding

        Returns:
            InvoiceResult with voiding details

        Raises:
            AccountingError: If voiding fails
        """
        pass

    async def apply_payment(
        self,
        invoice_id: str,
        amount: Decimal,
        payment_date: Optional[datetime] = None,
        payment_method: Optional[str] = None,
        reference: Optional[str] = None
    ) -> PaymentResult:
        """
        Apply a payment to an invoice.

        Args:
            invoice_id: Invoice ID to apply payment to
            amount: Payment amount
            payment_date: Date of payment
            payment_method: Payment method type
            reference: Payment reference number

        Returns:
            PaymentResult with payment details

        Raises:
            AccountingError: If payment application fails
        """
        raise NotImplementedError("Payment application not implemented for this accounting system")

    async def get_customer_by_id(self, customer_id: str) -> CustomerResult:
        """
        Get customer details from accounting system.

        Args:
            customer_id: Customer ID in accounting system

        Returns:
            CustomerResult with customer details

        Raises:
            AccountingError: If customer lookup fails
        """
        raise NotImplementedError("Customer lookup not implemented for this accounting system")

    async def search_customers(
        self,
        query: str,
        limit: int = 10
    ) -> List[CustomerResult]:
        """
        Search for customers in accounting system.

        Args:
            query: Search query (name, email, etc.)
            limit: Maximum number of results

        Returns:
            List of CustomerResult objects

        Raises:
            AccountingError: If search fails
        """
        raise NotImplementedError("Customer search not implemented for this accounting system")

    async def validate_connection(self) -> bool:
        """
        Validate connection to the accounting system.

        Returns:
            True if connection is valid

        Raises:
            AccountingError: If connection validation fails
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

    def get_supported_tax_types(self) -> List[str]:
        """
        Get list of supported tax types.

        Returns:
            List of supported tax type identifiers
        """
        # Default implementation - override in subclasses
        return ["VAT", "GST", "Sales Tax", "State Tax", "City Tax"]

    async def get_tax_rates(
        self,
        country: str,
        state: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None
    ) -> List[TaxCalculation]:
        """
        Get applicable tax rates for a location.

        Args:
            country: Country code
            state: State/province
            city: City name
            postal_code: Postal/ZIP code

        Returns:
            List of TaxCalculation objects

        Raises:
            AccountingError: If tax rate lookup fails
        """
        # Default implementation - override in subclasses
        return []


class AccountingAdapterFactory:
    """Factory for creating accounting adapter instances."""

    _adapters: Dict[AccountingSystemType, type] = {}

    @classmethod
    def register_adapter(
        cls,
        system_type: AccountingSystemType,
        adapter_class: type[AccountingAdapter]
    ):
        """Register an accounting adapter implementation."""
        cls._adapters[system_type] = adapter_class

    @classmethod
    def create_adapter(
        cls,
        system_type: AccountingSystemType,
        **config
    ) -> AccountingAdapter:
        """Create an accounting adapter instance."""
        if system_type not in cls._adapters:
            raise ValueError(f"Unsupported accounting system: {system_type}")

        adapter_class = cls._adapters[system_type]
        return adapter_class(**config)

    @classmethod
    def get_supported_systems(cls) -> List[AccountingSystemType]:
        """Get list of registered accounting system types."""
        return list(cls._adapters.keys())


# Register built-in adapters when they are imported
def _register_builtin_adapters():
    """Register built-in adapter implementations."""
    try:
        from .quickbooks_adapter import QuickBooksAdapter
        AccountingAdapterFactory.register_adapter(AccountingSystemType.QUICKBOOKS, QuickBooksAdapter)
    except ImportError:
        pass

    try:
        from .netsuite_adapter import NetSuiteAdapter
        AccountingAdapterFactory.register_adapter(AccountingSystemType.NETSUITE, NetSuiteAdapter)
    except ImportError:
        pass

    try:
        from .sap_adapter import SAPAdapter
        AccountingAdapterFactory.register_adapter(AccountingSystemType.SAP, SAPAdapter)
    except ImportError:
        pass


# Register adapters when module is imported
_register_builtin_adapters()