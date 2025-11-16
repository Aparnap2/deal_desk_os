"""
Invoice Management API Routes

Endpoints for creating, managing, and posting invoices in the Deal Desk OS.
Supports the complete invoice lifecycle from staging to accounting system integration.
"""

from datetime import timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_db
from app.models.invoice import (
    AccountingSystemType,
    Invoice,
    InvoiceStatus,
    InvoiceStaging,
    InvoiceStagingStatus,
)
from app.models.user import User
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["invoices"])


Pagination = Annotated[int, Query(ge=1)]


@router.post("/stage")
async def create_staged_invoice(
    deal_id: str,
    accounting_system: AccountingSystemType,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a staged invoice from a closed-won deal."""
    invoice_service = InvoiceService(session)

    try:
        staged_invoice, line_items, tax_calculations = await invoice_service.create_staged_invoice(
            deal_id=deal_id,
            accounting_system=accounting_system,
            user_id=current_user.id,
        )

        return {
            "id": staged_invoice.id,
            "invoice_number": staged_invoice.invoice_number,
            "status": staged_invoice.status.value,
            "deal_id": staged_invoice.deal_id,
            "customer_name": staged_invoice.customer_name,
            "total_amount": float(staged_invoice.total_amount),
            "currency": staged_invoice.currency,
            "created_at": staged_invoice.created_at.isoformat(),
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create staged invoice: {str(e)}"
        )


@router.get("/stage")
async def list_staged_invoices(
    page: Pagination = 1,
    page_size: Pagination = Query(default=20, le=100, ge=1),
    deal_id: Optional[str] = None,
    status: Optional[InvoiceStagingStatus] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 - scope checks hook point
) -> dict:
    """List staged invoices with optional filtering."""
    invoice_service = InvoiceService(session)

    offset = (page - 1) * page_size
    staged_invoices = await invoice_service.get_staged_invoices(
        deal_id=deal_id,
        status=status,
        limit=page_size,
        offset=offset,
    )

    # Get total count for pagination
    count_query = select(func.count(InvoiceStaging.id))
    if deal_id:
        count_query = count_query.where(InvoiceStaging.deal_id == deal_id)
    if status:
        count_query = count_query.where(InvoiceStaging.status == status)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    items = []
    for invoice in staged_invoices:
        items.append({
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "status": invoice.status.value,
            "deal_id": invoice.deal_id,
            "customer_name": invoice.customer_name,
            "total_amount": float(invoice.total_amount),
            "currency": invoice.currency,
            "created_at": invoice.created_at.isoformat(),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stage/{staged_invoice_id}")
async def get_staged_invoice(
    staged_invoice_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> dict:
    """Get a specific staged invoice by ID."""
    result = await session.execute(
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staged invoice not found"
        )

    # Load line items
    line_items = []
    for item in staged_invoice.line_items:
        line_items.append({
            "id": item.id,
            "line_number": item.line_number,
            "description": item.description,
            "sku": item.sku,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "line_total": float(item.line_total),
            "tax_amount": float(item.tax_amount),
        })

    # Load tax calculations
    tax_calculations = []
    for tax in staged_invoice.tax_calculations:
        tax_calculations.append({
            "id": tax.id,
            "tax_name": tax.tax_name,
            "tax_rate": float(tax.tax_rate),
            "taxable_amount": float(tax.taxable_amount),
            "tax_amount": float(tax.tax_amount),
        })

    return {
        "id": staged_invoice.id,
        "invoice_number": staged_invoice.invoice_number,
        "status": staged_invoice.status.value,
        "deal_id": staged_invoice.deal_id,
        "customer_name": staged_invoice.customer_name,
        "customer_email": staged_invoice.customer_email,
        "subtotal": float(staged_invoice.subtotal),
        "tax_amount": float(staged_invoice.tax_amount),
        "total_amount": float(staged_invoice.total_amount),
        "currency": staged_invoice.currency,
        "invoice_date": staged_invoice.invoice_date.isoformat(),
        "due_date": staged_invoice.due_date.isoformat(),
        "description": staged_invoice.description,
        "target_accounting_system": staged_invoice.target_accounting_system.value,
        "created_at": staged_invoice.created_at.isoformat(),
        "updated_at": staged_invoice.updated_at.isoformat(),
        "line_items": line_items,
        "tax_calculations": tax_calculations,
        "preview_data": staged_invoice.preview_data,
    }


@router.post("/stage/{staged_invoice_id}/submit")
async def submit_invoice_for_approval(
    staged_invoice_id: str,
    notes: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Submit a staged invoice for approval."""
    invoice_service = InvoiceService(session)

    try:
        staged_invoice = await invoice_service.submit_for_approval(
            staged_invoice_id=staged_invoice_id,
            user_id=current_user.id,
            notes=notes,
        )

        return {
            "id": staged_invoice.id,
            "invoice_number": staged_invoice.invoice_number,
            "status": staged_invoice.status.value,
            "submitted_for_approval_at": staged_invoice.submitted_for_approval_at.isoformat() if staged_invoice.submitted_for_approval_at else None,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/stage/{staged_invoice_id}/approve")
async def approve_staged_invoice(
    staged_invoice_id: str,
    notes: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Approve a staged invoice."""
    invoice_service = InvoiceService(session)

    try:
        staged_invoice = await invoice_service.approve_invoice(
            staged_invoice_id=staged_invoice_id,
            user_id=current_user.id,
            notes=notes,
        )

        return {
            "id": staged_invoice.id,
            "invoice_number": staged_invoice.invoice_number,
            "status": staged_invoice.status.value,
            "approved_at": staged_invoice.approved_at.isoformat() if staged_invoice.approved_at else None,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/stage/{staged_invoice_id}/reject")
async def reject_staged_invoice(
    staged_invoice_id: str,
    reason: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Reject a staged invoice."""
    invoice_service = InvoiceService(session)

    try:
        staged_invoice = await invoice_service.reject_invoice(
            staged_invoice_id=staged_invoice_id,
            user_id=current_user.id,
            reason=reason,
        )

        return {
            "id": staged_invoice.id,
            "invoice_number": staged_invoice.invoice_number,
            "status": staged_invoice.status.value,
            "rejected_at": staged_invoice.rejected_at.isoformat() if staged_invoice.rejected_at else None,
            "rejection_reason": staged_invoice.rejection_reason,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/stage/{staged_invoice_id}/post")
async def post_invoice_to_accounting_system(
    staged_invoice_id: str,
    send_to_customer: bool = False,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Post an approved staged invoice to the accounting system."""
    invoice_service = InvoiceService(session)

    try:
        invoice, _ = await invoice_service.post_to_accounting_system(
            staged_invoice_id=staged_invoice_id,
            user_id=current_user.id,
            send_to_customer=send_to_customer,
        )

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "status": invoice.status.value,
            "accounting_system": invoice.accounting_system.value,
            "erp_invoice_id": invoice.erp_invoice_id,
            "erp_url": invoice.erp_url,
            "posted_at": invoice.posted_at.isoformat(),
            "total_amount": float(invoice.total_amount),
            "currency": invoice.currency,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to post invoice: {str(e)}"
        )


@router.get("")
async def list_invoices(
    page: Pagination = 1,
    page_size: Pagination = Query(default=20, le=100, ge=1),
    deal_id: Optional[str] = None,
    status: Optional[InvoiceStatus] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 - scope checks hook point
) -> dict:
    """List posted invoices with optional filtering."""
    invoice_service = InvoiceService(session)

    offset = (page - 1) * page_size
    invoices = await invoice_service.get_invoices(
        deal_id=deal_id,
        status=status,
        limit=page_size,
        offset=offset,
    )

    # Get total count for pagination
    count_query = select(func.count(Invoice.id))
    if deal_id:
        count_query = count_query.where(Invoice.deal_id == deal_id)
    if status:
        count_query = count_query.where(Invoice.status == status)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    items = []
    for invoice in invoices:
        items.append({
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "status": invoice.status.value,
            "deal_id": invoice.deal_id,
            "customer_name": invoice.customer_name,
            "total_amount": float(invoice.total_amount),
            "currency": invoice.currency,
            "accounting_system": invoice.accounting_system.value,
            "posted_at": invoice.posted_at.isoformat(),
            "erp_invoice_id": invoice.erp_invoice_id,
            "erp_url": invoice.erp_url,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> dict:
    """Get a specific posted invoice by ID."""
    result = await session.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.tax_calculations),
            selectinload(Invoice.deal),
        )
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    # Load line items
    line_items = []
    for item in invoice.line_items:
        line_items.append({
            "id": item.id,
            "line_number": item.line_number,
            "description": item.description,
            "sku": item.sku,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "line_total": float(item.line_total),
            "tax_amount": float(item.tax_amount),
        })

    # Load tax calculations
    tax_calculations = []
    for tax in invoice.tax_calculations:
        tax_calculations.append({
            "id": tax.id,
            "tax_name": tax.tax_name,
            "tax_rate": float(tax.tax_rate),
            "taxable_amount": float(tax.taxable_amount),
            "tax_amount": float(tax.tax_amount),
        })

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status.value,
        "deal_id": invoice.deal_id,
        "customer_name": invoice.customer_name,
        "customer_email": invoice.customer_email,
        "subtotal": float(invoice.subtotal),
        "tax_amount": float(invoice.tax_amount),
        "total_amount": float(invoice.total_amount),
        "currency": invoice.currency,
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "description": invoice.description,
        "accounting_system": invoice.accounting_system.value,
        "erp_invoice_id": invoice.erp_invoice_id,
        "erp_url": invoice.erp_url,
        "posted_at": invoice.posted_at.isoformat(),
        "posting_response": invoice.posting_response,
        "paid_amount": float(invoice.paid_amount),
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "payment_reference": invoice.payment_reference,
        "created_at": invoice.created_at.isoformat(),
        "updated_at": invoice.updated_at.isoformat(),
        "line_items": line_items,
        "tax_calculations": tax_calculations,
    }


@router.get("/accounting-systems", response_model=List[AccountingSystemType])
async def get_supported_accounting_systems(
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> List[AccountingSystemType]:
    """Get list of supported accounting systems."""
    return list(AccountingSystemType)


@router.get("/deals/{deal_id}/invoice-eligibility")
async def check_deal_invoice_eligibility(
    deal_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> dict:
    """Check if a deal is eligible for invoice generation."""
    from app.models.deal import Deal, DealStage

    result = await session.execute(
        select(Deal).options(selectinload(Deal.payments)).where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found"
        )

    # Check eligibility criteria
    eligible = deal.stage == DealStage.CLOSED_WON

    # Additional checks
    existing_invoice = False
    if eligible:
        result = await session.execute(
            select(func.count(InvoiceStaging.id)).where(
                InvoiceStaging.deal_id == deal_id,
                InvoiceStaging.status.in_([
                    InvoiceStagingStatus.DRAFT,
                    InvoiceStagingStatus.PENDING_APPROVAL,
                    InvoiceStagingStatus.APPROVED
                ])
            )
        )
        existing_invoice_count = result.scalar()
        existing_invoice = existing_invoice_count > 0

    payment_collected = deal.payment_collected_at is not None

    return {
        "eligible": eligible and not existing_invoice,
        "deal_stage": deal.stage.value,
        "payment_collected": payment_collected,
        "existing_invoice": existing_invoice,
        "reason": (
            "Deal is not closed-won" if not eligible
            else "Invoice already exists" if existing_invoice
            else "Eligible for invoice generation"
        ),
    }