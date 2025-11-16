"""
Invoice and Invoice Staging Models

Models for managing the invoice lifecycle from staging to final posting
in the Deal Desk OS quote-to-cash workflow.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, List, Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


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


class InvoiceStagingStatus(str, Enum):
    """Invoice staging status enumeration."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"


class AccountingSystemType(str, Enum):
    """Supported accounting systems."""
    QUICKBOOKS = "quickbooks"
    NETSUITE = "netsuite"
    SAP = "sap"
    XERO = "xero"
    FRESHBOOKS = "freshbooks"
    WAVE = "wave"


class TaxCalculationType(str, Enum):
    """Tax calculation methods."""
    AUTO = "auto"  # Automatic calculation
    MANUAL = "manual"  # Manual entry
    EXEMPT = "exempt"  # Tax exempt


class InvoiceStaging(TimestampMixin, Base):
    """
    Staging table for invoices pending approval and posting.
    Allows for preview and validation before final posting to accounting systems.
    """
    __tablename__ = "invoice_staging"

    id: Mapped[Identifier]
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    status: Mapped[InvoiceStagingStatus] = mapped_column(
        SAEnum(InvoiceStagingStatus), default=InvoiceStagingStatus.DRAFT, nullable=False
    )

    # Invoice details
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    customer_tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Financial details
    subtotal: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    # Invoice metadata
    invoice_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(default=30, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Approval workflow
    submitted_for_approval_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ERP integration
    target_accounting_system: Mapped[AccountingSystemType] = mapped_column(
        SAEnum(AccountingSystemType), nullable=False
    )
    erp_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erp_item_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Tracking and validation
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    validation_errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preview_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Metadata
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invoice_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    deal: Mapped["Deal"] = relationship(back_populates="staged_invoices")
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by])
    rejecter: Mapped["User | None"] = relationship(foreign_keys=[rejected_by])
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])
    line_items: Mapped[list["InvoiceStagingLineItem"]] = relationship(
        back_populates="staging_invoice", cascade="all,delete-orphan"
    )
    tax_calculations: Mapped[list["InvoiceStagingTax"]] = relationship(
        back_populates="staging_invoice", cascade="all,delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="staged_invoice", cascade="all,delete-orphan"
    )

    __table_args__ = (
        Index("ix_invoice_staging_deal_status", "deal_id", "status"),
        Index("ix_invoice_staging_invoice_number", "invoice_number"),
        Index("ix_invoice_staging_created_at", "created_at"),
    )


class Invoice(TimestampMixin, Base):
    """
    Final posted invoices with ERP system references.
    Represents the canonical invoice record after successful posting.
    """
    __tablename__ = "invoices"

    id: Mapped[Identifier]
    staging_id: Mapped[str | None] = mapped_column(ForeignKey("invoice_staging.id", ondelete="SET NULL"), nullable=True, index=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus), default=InvoiceStatus.POSTED, nullable=False
    )

    # Financial details (copied from staging for audit)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Invoice metadata
    invoice_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ERP integration details
    accounting_system: Mapped[AccountingSystemType] = mapped_column(
        SAEnum(AccountingSystemType), nullable=False
    )
    erp_invoice_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    erp_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erp_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Posting details
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posted_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    posting_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Payment tracking
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Cancellation/void details
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit trail
    staging_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    invoice_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    staging_invoice: Mapped["InvoiceStaging | None"] = relationship(back_populates="final_invoices")
    deal: Mapped["Deal"] = relationship(back_populates="invoices")
    poster: Mapped["User | None"] = relationship(foreign_keys=[posted_by])
    voider: Mapped["User | None"] = relationship(foreign_keys=[voided_by])
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice", cascade="all,delete-orphan"
    )
    tax_calculations: Mapped[list["InvoiceTax"]] = relationship(
        back_populates="invoice", cascade="all,delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="invoice", cascade="all,delete-orphan"
    )

    __table_args__ = (
        Index("ix_invoice_deal_status", "deal_id", "status"),
        Index("ix_invoice_erp_id", "accounting_system", "erp_invoice_id"),
        Index("ix_invoice_posted_at", "posted_at"),
    )


class InvoiceStagingLineItem(TimestampMixin, Base):
    """Line items for staged invoices."""
    __tablename__ = "invoice_staging_line_items"

    id: Mapped[Identifier]
    staging_id: Mapped[str] = mapped_column(ForeignKey("invoice_staging.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(nullable=False)

    # Item details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=2), default=0, nullable=False)

    # Calculated amounts
    line_total: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    tax_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # VAT, GST, Sales Tax, etc.

    # ERP mapping
    erp_item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erp_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erp_tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Metadata
    invoice_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    staging_invoice: Mapped["InvoiceStaging"] = relationship(back_populates="line_items")


class InvoiceLineItem(TimestampMixin, Base):
    """Line items for final posted invoices."""
    __tablename__ = "invoice_line_items"

    id: Mapped[Identifier]
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    staging_line_item_id: Mapped[str | None] = mapped_column(ForeignKey("invoice_staging_line_items.id", ondelete="SET NULL"), nullable=True)
    line_number: Mapped[int] = mapped_column(nullable=False)

    # Item details (copied from staging for audit)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=2), default=0, nullable=False)

    # Calculated amounts
    line_total: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), default=0, nullable=False)
    tax_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ERP references
    erp_line_item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    erp_item_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    staging_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    invoice: Mapped["Invoice"] = relationship(back_populates="line_items")
    staging_line_item: Mapped["InvoiceStagingLineItem | None"] = relationship()


class InvoiceStagingTax(TimestampMixin, Base):
    """Tax calculations for staged invoices."""
    __tablename__ = "invoice_staging_taxes"

    id: Mapped[Identifier]
    staging_id: Mapped[str] = mapped_column(ForeignKey("invoice_staging.id", ondelete="CASCADE"), nullable=False, index=True)

    # Tax details
    tax_name: Mapped[str] = mapped_column(String(100), nullable=False)  # VAT, GST, State Tax, etc.
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(precision=8, scale=4), nullable=False)  # Percentage rate
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)

    # Tax jurisdiction
    tax_jurisdiction: Mapped[str | None] = mapped_column(String(100), nullable=True)  # State, Country, etc.
    tax_type: Mapped[TaxCalculationType] = mapped_column(
        SAEnum(TaxCalculationType), default=TaxCalculationType.AUTO, nullable=False
    )

    # ERP mapping
    erp_tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    erp_tax_account: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    invoice_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    staging_invoice: Mapped["InvoiceStaging"] = relationship(back_populates="tax_calculations")


class InvoiceTax(TimestampMixin, Base):
    """Tax calculations for final posted invoices."""
    __tablename__ = "invoice_taxes"

    id: Mapped[Identifier]
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    staging_tax_id: Mapped[str | None] = mapped_column(ForeignKey("invoice_staging_taxes.id", ondelete="SET NULL"), nullable=True)

    # Tax details (copied from staging for audit)
    tax_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(precision=8, scale=4), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)

    # Tax jurisdiction
    tax_jurisdiction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax_type: Mapped[TaxCalculationType] = mapped_column(
        SAEnum(TaxCalculationType), default=TaxCalculationType.AUTO, nullable=False
    )

    # ERP references
    erp_tax_line_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    staging_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    invoice: Mapped["Invoice"] = relationship(back_populates="tax_calculations")
    staging_tax: Mapped["InvoiceStagingTax | None"] = relationship()


class AccountingIntegration(Base):
    """Configuration for accounting system integrations."""
    __tablename__ = "accounting_integrations"

    id: Mapped[Identifier]
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    system_type: Mapped[AccountingSystemType] = mapped_column(SAEnum(AccountingSystemType), nullable=False)

    # Connection details
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    connection_config: Mapped[dict] = mapped_column(JSON, nullable=False)  # Encrypted credentials

    # Default settings
    default_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    default_tax_codes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_account_mapping: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Validation
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_result: Mapped[bool] = mapped_column(default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invoice_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    creator: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_accounting_integration_system_type", "system_type"),
        Index("ix_accounting_integration_active", "is_active"),
    )