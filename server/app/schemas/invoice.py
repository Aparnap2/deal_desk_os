"""
Invoice API Schemas

Pydantic models for invoice-related API requests and responses.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.invoice import (
    AccountingSystemType,
    InvoiceStatus,
    InvoiceStagingStatus,
    TaxCalculationType,
)


# Base Models

class BaseInvoiceLineItem(BaseModel):
    """Base schema for invoice line items."""
    description: str
    sku: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    tax_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class BaseInvoiceTax(BaseModel):
    """Base schema for invoice tax calculations."""
    tax_name: str
    tax_rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    tax_jurisdiction: Optional[str] = None
    tax_type: TaxCalculationType
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


# Invoice Staging Models

class InvoiceStagingLineItemRead(BaseInvoiceLineItem):
    """Schema for reading invoice staging line items."""
    id: str
    staging_id: str
    line_number: int
    line_total: Decimal
    erp_item_id: Optional[str] = None
    erp_account_id: Optional[str] = None
    erp_tax_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class InvoiceStagingTaxRead(BaseInvoiceTax):
    """Schema for reading invoice staging tax calculations."""
    id: str
    staging_id: str
    erp_tax_code: Optional[str] = None
    erp_tax_account: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class InvoiceStagingRead(BaseModel):
    """Schema for reading staged invoices."""
    id: str
    deal_id: str
    invoice_number: str
    status: InvoiceStagingStatus

    # Customer details
    customer_name: str
    customer_email: Optional[str] = None
    customer_address: Optional[Dict[str, Any]] = None
    customer_tax_id: Optional[str] = None

    # Financial details
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str

    # Invoice metadata
    invoice_date: datetime
    due_date: datetime
    payment_terms_days: int
    description: Optional[str] = None

    # Approval workflow
    submitted_for_approval_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None

    # ERP integration
    target_accounting_system: AccountingSystemType
    erp_customer_id: Optional[str] = None
    erp_item_mapping: Optional[Dict[str, Any]] = None

    # Tracking and validation
    idempotency_key: str
    validation_errors: Optional[Dict[str, Any]] = None
    preview_data: Optional[Dict[str, Any]] = None

    # Metadata
    created_by: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    # Nested relationships
    line_items: List[InvoiceStagingLineItemRead] = []
    tax_calculations: List[InvoiceStagingTaxRead] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceStagingCreateRequest(BaseModel):
    """Schema for creating a staged invoice."""
    deal_id: str
    accounting_system: AccountingSystemType
    custom_data: Optional[Dict[str, Any]] = None


class InvoiceStagingUpdateRequest(BaseModel):
    """Schema for updating a staged invoice."""
    description: Optional[str] = None
    payment_terms_days: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[Dict[str, Any]] = None
    custom_data: Optional[Dict[str, Any]] = None


class InvoiceStagingCollection(BaseModel):
    """Schema for a collection of staged invoices."""
    items: List[InvoiceStagingRead]
    total: int
    page: int
    page_size: int


# Posted Invoice Models

class InvoiceLineItemRead(BaseInvoiceLineItem):
    """Schema for reading posted invoice line items."""
    id: str
    invoice_id: str
    staging_line_item_id: Optional[str] = None
    line_number: int
    line_total: Decimal
    erp_line_item_id: Optional[str] = None
    erp_item_id: Optional[str] = None
    staging_snapshot: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class InvoiceTaxRead(BaseInvoiceTax):
    """Schema for reading posted invoice tax calculations."""
    id: str
    invoice_id: str
    staging_tax_id: Optional[str] = None
    erp_tax_line_id: Optional[str] = None
    staging_snapshot: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class InvoiceRead(BaseModel):
    """Schema for reading posted invoices."""
    id: str
    staging_id: Optional[str] = None
    deal_id: str
    invoice_number: str
    status: InvoiceStatus

    # Financial details
    customer_name: str
    customer_email: Optional[str] = None
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str

    # Invoice metadata
    invoice_date: datetime
    due_date: datetime
    description: Optional[str] = None

    # ERP integration details
    accounting_system: AccountingSystemType
    erp_invoice_id: Optional[str] = None
    erp_customer_id: Optional[str] = None
    erp_url: Optional[str] = None

    # Posting details
    posted_at: datetime
    posted_by: Optional[str] = None
    posting_response: Optional[Dict[str, Any]] = None

    # Payment tracking
    paid_amount: Decimal = Decimal("0")
    paid_at: Optional[datetime] = None
    payment_reference: Optional[str] = None

    # Cancellation/void details
    voided_at: Optional[datetime] = None
    voided_by: Optional[str] = None
    void_reason: Optional[str] = None

    # Audit trail
    staging_snapshot: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    # Nested relationships
    line_items: List[InvoiceLineItemRead] = []
    tax_calculations: List[InvoiceTaxRead] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceCollection(BaseModel):
    """Schema for a collection of posted invoices."""
    items: List[InvoiceRead]
    total: int
    page: int
    page_size: int


# Request Models

class PostInvoiceRequest(BaseModel):
    """Schema for posting an invoice to accounting system."""
    send_to_customer: bool = False


# Accounting Integration Models

class AccountingIntegrationRead(BaseModel):
    """Schema for reading accounting integration configuration."""
    id: str
    name: str
    system_type: AccountingSystemType
    is_active: bool
    default_currency: str = "USD"
    default_tax_codes: Optional[Dict[str, Any]] = None
    default_account_mapping: Optional[Dict[str, Any]] = None
    last_tested_at: Optional[datetime] = None
    test_result: bool = False
    error_message: Optional[str] = None
    created_by: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountingIntegrationCreateRequest(BaseModel):
    """Schema for creating accounting integration configuration."""
    name: str
    system_type: AccountingSystemType
    connection_config: Dict[str, Any]
    default_currency: str = "USD"
    default_tax_codes: Optional[Dict[str, Any]] = None
    default_account_mapping: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AccountingIntegrationUpdateRequest(BaseModel):
    """Schema for updating accounting integration configuration."""
    name: Optional[str] = None
    is_active: Optional[bool] = None
    connection_config: Optional[Dict[str, Any]] = None
    default_currency: Optional[str] = None
    default_tax_codes: Optional[Dict[str, Any]] = None
    default_account_mapping: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


# Summary Models for API Responses

class InvoiceSummary(BaseModel):
    """Brief summary of an invoice for list views."""
    id: str
    invoice_number: str
    status: InvoiceStatus
    customer_name: str
    total_amount: Decimal
    currency: str
    invoice_date: datetime
    due_date: datetime
    accounting_system: Optional[AccountingSystemType] = None
    posted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceStagingSummary(BaseModel):
    """Brief summary of a staged invoice for list views."""
    id: str
    invoice_number: str
    status: InvoiceStagingStatus
    customer_name: str
    total_amount: Decimal
    currency: str
    invoice_date: datetime
    due_date: datetime
    target_accounting_system: AccountingSystemType
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)