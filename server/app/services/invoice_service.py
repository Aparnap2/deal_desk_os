"""
Invoice Service

Core business logic for invoice generation, staging, and posting to accounting systems.
Handles the complete invoice lifecycle from deal closure to accounting system integration.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.integrations.accounting import (
    AccountingAdapterFactory,
    AccountingSystemType,
    CustomerDetails,
    InvoiceRequest,
    InvoiceResult,
    LineItem,
    TaxCalculation,
    TaxCalculationType,
)
from app.models.invoice import (
    AccountingIntegration,
    Invoice,
    InvoiceStatus,
    InvoiceStaging,
    InvoiceStagingLineItem,
    InvoiceStagingStatus,
    InvoiceStagingTax,
)
from app.models.deal import Deal, DealStage
from app.models.payment import PaymentStatus

logger = logging.getLogger(__name__)


class InvoiceService:
    """Service for managing invoice lifecycle and accounting integration."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_staged_invoice(
        self,
        deal_id: str,
        accounting_system: AccountingSystemType,
        user_id: Optional[str] = None,
        custom_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[InvoiceStaging, List[InvoiceStagingLineItem], List[InvoiceStagingTax]]:
        """
        Create a staged invoice from a closed-won deal.

        Args:
            deal_id: ID of the closed-won deal
            accounting_system: Target accounting system
            user_id: User creating the invoice
            custom_data: Optional custom invoice data

        Returns:
            Tuple of (staged_invoice, line_items, tax_calculations)

        Raises:
            ValueError: If deal is not eligible for invoicing
            RuntimeError: If invoice generation fails
        """
        # Load deal with related data
        result = await self.session.execute(
            select(Deal)
            .options(
                selectinload(Deal.payments),
                selectinload(Deal.owner),
                selectinload(Deal.approvals),
                selectinload(Deal.staged_invoices),
            )
            .where(Deal.id == deal_id)
        )
        deal = result.scalar_one_or_none()

        if not deal:
            raise ValueError(f"Deal not found: {deal_id}")

        if deal.stage != DealStage.CLOSED_WON:
            raise ValueError(f"Deal is not closed-won: {deal.stage}")

        # Check if invoice already exists for this deal
        existing_staged = await self.session.execute(
            select(InvoiceStaging).where(
                InvoiceStaging.deal_id == deal_id,
                InvoiceStaging.status.in_([
                    InvoiceStagingStatus.DRAFT,
                    InvoiceStagingStatus.PENDING_APPROVAL,
                    InvoiceStagingStatus.APPROVED
                ])
            )
        )
        if existing_staged.scalar_one_or_none():
            raise ValueError("Invoice already exists for this deal")

        # Generate invoice number
        invoice_number = await self._generate_invoice_number(deal)

        # Create idempotency key
        idempotency_key = self._generate_idempotency_key(deal_id, invoice_number)

        # Create staged invoice
        staged_invoice = InvoiceStaging(
            deal_id=deal_id,
            invoice_number=invoice_number,
            status=InvoiceStagingStatus.DRAFT,
            customer_name=deal.name,
            customer_email=deal.owner.email if deal.owner else None,
            subtotal=deal.amount,
            total_amount=deal.amount,
            currency=deal.currency,
            invoice_date=datetime.utcnow(),
            due_date=datetime.utcnow() + timedelta(days=deal.payment_terms_days),
            payment_terms_days=deal.payment_terms_days,
            description=f"Invoice for deal: {deal.name}",
            target_accounting_system=accounting_system,
            idempotency_key=idempotency_key,
            created_by=user_id,
            metadata=custom_data or {},
        )

        # Create line items from deal
        line_items = await self._create_line_items_from_deal(staged_invoice, deal)

        # Calculate taxes
        tax_calculations = await self._calculate_taxes(staged_invoice, line_items, deal)

        # Update totals with taxes
        total_tax = sum(tax.tax_amount for tax in tax_calculations)
        staged_invoice.tax_amount = total_tax
        staged_invoice.total_amount = staged_invoice.subtotal + total_tax

        # Save to database
        self.session.add(staged_invoice)
        for item in line_items:
            self.session.add(item)
        for tax in tax_calculations:
            self.session.add(tax)

        await self.session.flush()

        # Update deal with invoice generation timestamp
        if not deal.invoice_generated_at:
            deal.invoice_generated_at = datetime.utcnow()

        # Generate preview data
        staged_invoice.preview_data = await self._generate_preview_data(
            staged_invoice, line_items, tax_calculations
        )

        await self.session.commit()

        logger.info(f"Created staged invoice {invoice_number} for deal {deal_id}")
        return staged_invoice, line_items, tax_calculations

    async def _generate_invoice_number(self, deal: Deal) -> str:
        """Generate a unique invoice number."""
        # Format: INV-YYYYMMDD-XXXXX (where XXXXX is sequential)
        date_str = datetime.utcnow().strftime("%Y%m%d")

        # Get the next sequence number for today
        result = await self.session.execute(
            select(func.count(InvoiceStaging.id)).where(
                func.date(InvoiceStaging.created_at) == datetime.utcnow().date()
            )
        )
        count = result.scalar() + 1

        return f"INV-{date_str}-{count:05d}"

    def _generate_idempotency_key(self, deal_id: str, invoice_number: str) -> str:
        """Generate a unique idempotency key for the invoice."""
        key_data = f"{deal_id}:{invoice_number}:{datetime.utcnow().isoformat()}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:64]

    async def _create_line_items_from_deal(
        self,
        staged_invoice: InvoiceStaging,
        deal: Deal
    ) -> List[InvoiceStagingLineItem]:
        """Create line items from deal data."""
        line_items = []

        # Main service/product line item
        main_item = InvoiceStagingLineItem(
            staging_id=staged_invoice.id,
            line_number=1,
            description=f"Professional Services - {deal.name}",
            sku="SRV-001",
            quantity=Decimal("1"),
            unit_price=deal.amount,
            line_total=deal.amount,
            tax_amount=Decimal("0"),
            metadata={"source": "deal_main", "deal_id": deal.id},
        )
        line_items.append(main_item)

        # Add operational cost as separate line item if applicable
        if deal.operational_cost and deal.operational_cost > 0:
            cost_item = InvoiceStagingLineItem(
                staging_id=staged_invoice.id,
                line_number=len(line_items) + 1,
                description="Operational & Infrastructure Costs",
                sku="OPS-001",
                quantity=Decimal("1"),
                unit_price=deal.operational_cost,
                line_total=deal.operational_cost,
                tax_amount=Decimal("0"),
                metadata={"source": "operational_cost", "deal_id": deal.id},
            )
            line_items.append(cost_item)

        return line_items

    async def _calculate_taxes(
        self,
        staged_invoice: InvoiceStaging,
        line_items: List[InvoiceStagingLineItem],
        deal: Deal
    ) -> List[InvoiceStagingTax]:
        """Calculate taxes for the invoice."""
        tax_calculations = []

        # Default tax calculation (can be enhanced with location-based tax logic)
        taxable_amount = sum(item.line_total for item in line_items)

        # Apply standard tax rate (can be made configurable)
        tax_rate = Decimal("8.25")  # 8.25% sales tax (example)
        tax_amount = (taxable_amount * tax_rate) / Decimal("100")

        tax = InvoiceStagingTax(
            staging_id=staged_invoice.id,
            tax_name="Sales Tax",
            tax_rate=tax_rate,
            taxable_amount=taxable_amount,
            tax_amount=tax_amount,
            tax_jurisdiction="State",
            tax_type=TaxCalculationType.AUTO,
        )
        tax_calculations.append(tax)

        return tax_calculations

    async def _generate_preview_data(
        self,
        staged_invoice: InvoiceStaging,
        line_items: List[InvoiceStagingLineItem],
        tax_calculations: List[InvoiceStagingTax]
    ) -> Dict[str, Any]:
        """Generate preview data for the staged invoice."""
        return {
            "customer": {
                "name": staged_invoice.customer_name,
                "email": staged_invoice.customer_email,
                "address": staged_invoice.customer_address,
            },
            "invoice": {
                "number": staged_invoice.invoice_number,
                "date": staged_invoice.invoice_date.isoformat(),
                "due_date": staged_invoice.due_date.isoformat(),
                "payment_terms_days": staged_invoice.payment_terms_days,
                "description": staged_invoice.description,
            },
            "amounts": {
                "subtotal": float(staged_invoice.subtotal),
                "tax_amount": float(staged_invoice.tax_amount),
                "total_amount": float(staged_invoice.total_amount),
                "currency": staged_invoice.currency,
            },
            "line_items": [
                {
                    "line_number": item.line_number,
                    "description": item.description,
                    "sku": item.sku,
                    "quantity": float(item.quantity),
                    "unit_price": float(item.unit_price),
                    "line_total": float(item.line_total),
                }
                for item in line_items
            ],
            "taxes": [
                {
                    "tax_name": tax.tax_name,
                    "tax_rate": float(tax.tax_rate),
                    "taxable_amount": float(tax.taxable_amount),
                    "tax_amount": float(tax.tax_amount),
                }
                for tax in tax_calculations
            ],
            "accounting_system": staged_invoice.target_accounting_system.value,
        }

    async def submit_for_approval(
        self,
        staged_invoice_id: str,
        user_id: str,
        notes: Optional[str] = None
    ) -> InvoiceStaging:
        """Submit a staged invoice for approval."""
        result = await self.session.execute(
            select(InvoiceStaging).where(InvoiceStaging.id == staged_invoice_id)
        )
        staged_invoice = result.scalar_one_or_none()

        if not staged_invoice:
            raise ValueError(f"Staged invoice not found: {staged_invoice_id}")

        if staged_invoice.status != InvoiceStagingStatus.DRAFT:
            raise ValueError(f"Cannot submit invoice in status: {staged_invoice.status}")

        staged_invoice.status = InvoiceStagingStatus.PENDING_APPROVAL
        staged_invoice.submitted_for_approval_at = datetime.utcnow()
        if notes:
            staged_invoice.metadata["approval_notes"] = notes

        await self.session.commit()

        logger.info(f"Submitted invoice {staged_invoice.invoice_number} for approval")
        return staged_invoice

    async def approve_invoice(
        self,
        staged_invoice_id: str,
        user_id: str,
        notes: Optional[str] = None
    ) -> InvoiceStaging:
        """Approve a staged invoice."""
        result = await self.session.execute(
            select(InvoiceStaging).where(InvoiceStaging.id == staged_invoice_id)
        )
        staged_invoice = result.scalar_one_or_none()

        if not staged_invoice:
            raise ValueError(f"Staged invoice not found: {staged_invoice_id}")

        if staged_invoice.status != InvoiceStagingStatus.PENDING_APPROVAL:
            raise ValueError(f"Cannot approve invoice in status: {staged_invoice.status}")

        staged_invoice.status = InvoiceStagingStatus.APPROVED
        staged_invoice.approved_at = datetime.utcnow()
        staged_invoice.approved_by = user_id
        if notes:
            staged_invoice.metadata["approval_notes"] = notes

        await self.session.commit()

        logger.info(f"Approved invoice {staged_invoice.invoice_number}")
        return staged_invoice

    async def reject_invoice(
        self,
        staged_invoice_id: str,
        user_id: str,
        reason: str
    ) -> InvoiceStaging:
        """Reject a staged invoice."""
        result = await self.session.execute(
            select(InvoiceStaging).where(InvoiceStaging.id == staged_invoice_id)
        )
        staged_invoice = result.scalar_one_or_none()

        if not staged_invoice:
            raise ValueError(f"Staged invoice not found: {staged_invoice_id}")

        if staged_invoice.status != InvoiceStagingStatus.PENDING_APPROVAL:
            raise ValueError(f"Cannot reject invoice in status: {staged_invoice.status}")

        staged_invoice.status = InvoiceStagingStatus.REJECTED
        staged_invoice.rejected_at = datetime.utcnow()
        staged_invoice.rejected_by = user_id
        staged_invoice.rejection_reason = reason

        await self.session.commit()

        logger.info(f"Rejected invoice {staged_invoice.invoice_number}: {reason}")
        return staged_invoice

    async def post_to_accounting_system(
        self,
        staged_invoice_id: str,
        user_id: str,
        send_to_customer: bool = False
    ) -> Tuple[Invoice, InvoiceResult]:
        """Post an approved staged invoice to the accounting system."""
        # Load staged invoice with line items and taxes
        result = await self.session.execute(
            select(InvoiceStaging)
            .options(
                selectinload(InvoiceStaging.line_items),
                selectinload(InvoiceStaging.tax_calculations),
                selectinload(InvoiceStaging.deal),
            )
            .where(InvoiceStaging.id == staged_invoice_id)
        )
        staged_invoice = result.scalar_one_or_none()

        if not staged_invoice:
            raise ValueError(f"Staged invoice not found: {staged_invoice_id}")

        if staged_invoice.status != InvoiceStagingStatus.APPROVED:
            raise ValueError(f"Cannot post invoice in status: {staged_invoice.status}")

        # Get accounting integration config
        accounting_integration = await self._get_accounting_integration(
            staged_invoice.target_accounting_system
        )

        if not accounting_integration or not accounting_integration.is_active:
            raise ValueError(f"Accounting integration not available for {staged_invoice.target_accounting_system}")

        # Create accounting adapter
        adapter = AccountingAdapterFactory.create_adapter(
            staged_invoice.target_accounting_system,
            **accounting_integration.connection_config
        )

        # Prepare invoice request
        invoice_request = await self._build_invoice_request(staged_invoice)

        try:
            # Post to accounting system
            invoice_result = await adapter.create_invoice(
                invoice_request,
                draft=False,  # Post directly since it's approved
            )

            if not invoice_result.success:
                raise RuntimeError(f"Failed to post invoice: {invoice_result.error_message}")

            # Create final invoice record
            invoice = Invoice(
                staging_id=staged_invoice_id,
                deal_id=staged_invoice.deal_id,
                invoice_number=invoice_result.invoice_number or staged_invoice.invoice_number,
                status=InvoiceStatus.POSTED,
                customer_name=staged_invoice.customer_name,
                customer_email=staged_invoice.customer_email,
                subtotal=staged_invoice.subtotal,
                tax_amount=staged_invoice.tax_amount,
                total_amount=staged_invoice.total_amount,
                currency=staged_invoice.currency,
                invoice_date=staged_invoice.invoice_date,
                due_date=staged_invoice.due_date,
                description=staged_invoice.description,
                accounting_system=staged_invoice.target_accounting_system,
                erp_invoice_id=invoice_result.invoice_id,
                erp_url=invoice_result.invoice_url,
                posted_at=datetime.utcnow(),
                posted_by=user_id,
                posting_response=invoice_result.gateway_response,
                staging_snapshot=staged_invoice.preview_data,
            )

            # Create final line items and tax records
            await self._create_final_invoice_records(invoice, staged_invoice)

            # Update staged invoice status
            staged_invoice.status = InvoiceStagingStatus.POSTED

            # Update deal
            if staged_invoice.deal:
                staged_invoice.deal.last_invoiced_at = datetime.utcnow()

            self.session.add(invoice)
            await self.session.commit()

            logger.info(f"Successfully posted invoice {invoice.invoice_number} to {staged_invoice.target_accounting_system}")
            return invoice, invoice_result

        except Exception as e:
            logger.error(f"Failed to post invoice to accounting system: {e}")
            raise

    async def _get_accounting_integration(
        self,
        system_type: AccountingSystemType
    ) -> Optional[AccountingIntegration]:
        """Get active accounting integration configuration."""
        result = await self.session.execute(
            select(AccountingIntegration).where(
                AccountingIntegration.system_type == system_type,
                AccountingIntegration.is_active == True
            )
        )
        return result.scalar_one_or_none()

    async def _build_invoice_request(
        self,
        staged_invoice: InvoiceStaging
    ) -> InvoiceRequest:
        """Build invoice request from staged invoice."""
        customer_details = CustomerDetails(
            name=staged_invoice.customer_name,
            email=staged_invoice.customer_email,
            address=staged_invoice.customer_address,
            tax_id=staged_invoice.customer_tax_id,
            currency=staged_invoice.currency,
            payment_terms_days=staged_invoice.payment_terms_days,
        )

        line_items = [
            LineItem(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                sku=item.sku,
                discount_percent=item.discount_percent,
                tax_amount=item.tax_amount,
                tax_type=item.tax_type,
                erp_item_id=item.erp_item_id,
                erp_account_id=item.erp_account_id,
                erp_tax_code=item.erp_tax_code,
            )
            for item in staged_invoice.line_items
        ]

        tax_calculations = [
            TaxCalculation(
                tax_name=tax.tax_name,
                tax_rate=tax.tax_rate,
                taxable_amount=tax.taxable_amount,
                tax_amount=tax.tax_amount,
                tax_jurisdiction=tax.tax_jurisdiction,
                tax_type=tax.tax_type,
                erp_tax_code=tax.erp_tax_code,
                erp_tax_account=tax.erp_tax_account,
            )
            for tax in staged_invoice.tax_calculations
        ]

        return InvoiceRequest(
            invoice_number=staged_invoice.invoice_number,
            customer=customer_details,
            line_items=line_items,
            tax_calculations=tax_calculations,
            invoice_date=staged_invoice.invoice_date,
            due_date=staged_invoice.due_date,
            description=staged_invoice.description,
            currency=staged_invoice.currency,
            payment_terms_days=staged_invoice.payment_terms_days,
            metadata=staged_invoice.metadata,
        )

    async def _create_final_invoice_records(
        self,
        invoice: Invoice,
        staged_invoice: InvoiceStaging
    ) -> None:
        """Create final invoice line items and tax records."""
        # Create final line items
        for i, staged_item in enumerate(staged_invoice.line_items):
            final_item = InvoiceLineItem(
                invoice_id=invoice.id,
                staging_line_item_id=staged_item.id,
                line_number=i + 1,
                description=staged_item.description,
                sku=staged_item.sku,
                quantity=staged_item.quantity,
                unit_price=staged_item.unit_price,
                discount_percent=staged_item.discount_percent,
                line_total=staged_item.line_total,
                tax_amount=staged_item.tax_amount,
                tax_type=staged_item.tax_type,
                staging_snapshot={
                    "description": staged_item.description,
                    "quantity": float(staged_item.quantity),
                    "unit_price": float(staged_item.unit_price),
                    "line_total": float(staged_item.line_total),
                },
            )
            self.session.add(final_item)

        # Create final tax records
        for staged_tax in staged_invoice.tax_calculations:
            final_tax = InvoiceTax(
                invoice_id=invoice.id,
                staging_tax_id=staged_tax.id,
                tax_name=staged_tax.tax_name,
                tax_rate=staged_tax.tax_rate,
                taxable_amount=staged_tax.taxable_amount,
                tax_amount=staged_tax.tax_amount,
                tax_jurisdiction=staged_tax.tax_jurisdiction,
                tax_type=staged_tax.tax_type,
                staging_snapshot={
                    "tax_name": staged_tax.tax_name,
                    "tax_rate": float(staged_tax.tax_rate),
                    "taxable_amount": float(staged_tax.taxable_amount),
                    "tax_amount": float(staged_tax.tax_amount),
                },
            )
            self.session.add(final_tax)

    async def get_staged_invoices(
        self,
        deal_id: Optional[str] = None,
        status: Optional[InvoiceStagingStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[InvoiceStaging]:
        """Get staged invoices with optional filtering."""
        query = select(InvoiceStaging).options(
            selectinload(InvoiceStaging.line_items),
            selectinload(InvoiceStaging.tax_calculations),
            selectinload(InvoiceStaging.deal),
        )

        if deal_id:
            query = query.where(InvoiceStaging.deal_id == deal_id)

        if status:
            query = query.where(InvoiceStaging.status == status)

        query = query.order_by(InvoiceStaging.created_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_invoices(
        self,
        deal_id: Optional[str] = None,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Invoice]:
        """Get posted invoices with optional filtering."""
        query = select(Invoice).options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.tax_calculations),
            selectinload(Invoice.deal),
        )

        if deal_id:
            query = query.where(Invoice.deal_id == deal_id)

        if status:
            query = query.where(Invoice.status == status)

        query = query.order_by(Invoice.posted_at.desc()).offset(offset).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()