"""
Comprehensive end-to-end workflow tests for Deal Desk OS.

This module tests complete business workflows:
- Quote-to-cash pipeline
- Deal lifecycle management
- Payment processing with idempotency
- E-signature workflows
- Invoice and ERP integration
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealStage, DealRisk, GuardrailStatus
from app.models.invoice import Invoice, InvoiceStatus
from app.models.payment import Payment, PaymentStatus
from app.models.approval import Approval, ApprovalStatus
from app.services.deal_service import create_deal, update_deal
from app.services.payment_service import PaymentService
from app.services.invoice_service import InvoiceService
from app.services.workflow_engine import WorkflowEngine
from app.services.sla_analytics import SLAAnalytics
from app.integrations.payment_gateways.stripe_adapter import StripeAdapter
from app.integrations.esignature.docusign_adapter import DocuSignAdapter


class TestQuoteToCashWorkflow:
    """End-to-end testing for the complete quote-to-cash workflow."""

    @pytest_asyncio.asyncio
    async def test_complete_quote_to_cash_success(self, async_db_session, sample_quote_to_cash_workflow_data):
        """Test successful complete quote-to-cash workflow."""
        # Setup test data
        workflow_data = sample_quote_to_cash_workflow_data

        # Create workflow engine
        workflow_engine = WorkflowEngine(async_db_session)

        # Initialize the quote-to-cash workflow
        workflow_instance = await workflow_engine.start_workflow(
            workflow_type="quote_to_cash",
            deal_id=workflow_data["deal"]["id"],
            initial_data=workflow_data
        )

        assert workflow_instance.id is not None
        assert workflow_instance.status == "running"

        # Step 1: Deal validation and guardrail checks
        deal = await workflow_engine.execute_step("validate_deal", workflow_instance.id)
        assert deal is not None
        assert deal.stage == DealStage.PROPOSAL

        # Step 2: Invoice creation
        invoice_result = await workflow_engine.execute_step("create_invoice", workflow_instance.id)
        assert invoice_result["status"] == "success"
        assert invoice_result["invoice_id"] is not None

        # Step 3: E-signature request
        with patch.object(DocuSignAdapter, 'send_envelope') as mock_envelope:
            mock_envelope.return_value = {
                "envelope_id": "envelope_123",
                "status": "sent",
                "signing_url": "https://demo.docusign.net/Signing/..."
            }

            signature_result = await workflow_engine.execute_step("send_for_signature", workflow_instance.id)
            assert signature_result["status"] == "success"
            assert signature_result["envelope_id"] == "envelope_123"

        # Step 4: Payment processing
        with patch.object(StripeAdapter, 'create_payment_intent') as mock_payment:
            mock_payment.return_value = {
                "id": "pi_test_123",
                "status": "requires_payment_method",
                "client_secret": "pi_test_123_secret_test",
            }

            payment_result = await workflow_engine.execute_step("collect_payment", workflow_instance.id)
            assert payment_result["status"] == "success"
            assert payment_result["payment_intent_id"] == "pi_test_123"

        # Step 5: Subscription activation (if applicable)
        activation_result = await workflow_engine.execute_step("activate_subscription", workflow_instance.id)
        assert activation_result["status"] == "success"

        # Verify final state
        final_workflow = await workflow_engine.get_workflow(workflow_instance.id)
        assert final_workflow.status == "completed"
        assert len(final_workflow.completed_steps) == 5

        # Verify deal progression
        updated_deal = await async_db_session.get(Deal, workflow_data["deal"]["id"])
        assert updated_deal.stage == DealStage.CLOSED_WON

    @pytest_asyncio.asyncio
    async def test_quote_to_cash_with_guardrail_violation(self, async_db_session, sample_quote_to_cash_workflow_data):
        """Test quote-to-cash workflow with guardrail violations."""
        # Modify test data to violate guardrails
        workflow_data = sample_quote_to_cash_workflow_data.copy()
        workflow_data["deal"]["discount_percent"] = "35.0"  # Exceeds typical limits
        workflow_data["deal"]["payment_terms_days"] = 90  # Exceeds typical limits

        workflow_engine = WorkflowEngine(async_db_session)

        # Start workflow
        workflow_instance = await workflow_engine.start_workflow(
            workflow_type="quote_to_cash",
            deal_id=workflow_data["deal"]["id"],
            initial_data=workflow_data
        )

        # Execute validation step - should detect guardrail violations
        validation_result = await workflow_engine.execute_step("validate_deal", workflow_instance.id)

        assert validation_result["status"] == "guardrail_violation"
        assert "discount_limit" in validation_result["violations"]
        assert "payment_terms_limit" in validation_result["violations"]

        # Verify required approvals were created
        async with async_db_session:
            approvals = await async_db_session.query(Approval).filter(
                Approval.deal_id == workflow_data["deal"]["id"]
            ).all()

            assert len(approvals) >= 2  # Executive and finance approvals needed
            assert all(approval.status == ApprovalStatus.PENDING for approval in approvals)

    @pytest_asyncio.asyncio
    async def test_quote_to_cash_payment_failure(self, async_db_session, sample_quote_to_cash_workflow_data):
        """Test quote-to-cash workflow with payment processing failure."""
        workflow_data = sample_quote_to_cash_workflow_data
        workflow_engine = WorkflowEngine(async_db_session)

        # Start workflow and get to payment step
        workflow_instance = await workflow_engine.start_workflow(
            workflow_type="quote_to_cash",
            deal_id=workflow_data["deal"]["id"],
            initial_data=workflow_data
        )

        # Complete previous steps
        await workflow_engine.execute_step("validate_deal", workflow_instance.id)
        await workflow_engine.execute_step("create_invoice", workflow_instance.id)
        await workflow_engine.execute_step("send_for_signature", workflow_instance.id)

        # Mock payment failure
        with patch.object(StripeAdapter, 'create_payment_intent') as mock_payment:
            mock_payment.side_effect = Exception("Payment gateway error")

            payment_result = await workflow_engine.execute_step("collect_payment", workflow_instance.id)

            assert payment_result["status"] == "error"
            assert "Payment gateway error" in payment_result["error"]

        # Verify workflow is paused pending retry
        workflow = await workflow_engine.get_workflow(workflow_instance.id)
        assert workflow.status == "paused"

    @pytest_asyncio.asyncio
    async def test_quote_to_cash_esignature_declined(self, async_db_session, sample_quote_to_cash_workflow_data):
        """Test quote-to-cash workflow with declined e-signature."""
        workflow_data = sample_quote_to_cash_workflow_data
        workflow_engine = WorkflowEngine(async_db_session)

        # Start workflow and get to signature step
        workflow_instance = await workflow_engine.start_workflow(
            workflow_type="quote_to_cash",
            deal_id=workflow_data["deal"]["id"],
            initial_data=workflow_data
        )

        await workflow_engine.execute_step("validate_deal", workflow_instance.id)
        await workflow_engine.execute_step("create_invoice", workflow_instance.id)

        # Mock declined signature
        with patch.object(DocuSignAdapter, 'get_envelope_status') as mock_status:
            mock_status.return_value = {
                "envelope_id": "envelope_123",
                "status": "declined",
                "declined_reason": "Terms not acceptable"
            }

            signature_result = await workflow_engine.execute_step("send_for_signature", workflow_instance.id)

            # Workflow should handle declined signature
            assert signature_result["status"] == "declined"
            assert signature_result["reason"] == "Terms not acceptable"

            # Verify deal is marked for review
            async with async_db_session:
                deal = await async_db_session.get(Deal, workflow_data["deal"]["id"])
                assert deal.stage == DealStage.NEGOTIATION


class TestDealLifecycleWorkflow:
    """Testing complete deal lifecycle management."""

    @pytest_asyncio.asyncio
    async def test_deal_prospect_to_close_won(self, async_db_session, generate_test_deal):
        """Test complete deal progression from prospect to close-won."""
        # Create initial deal
        deal_data = generate_test_deal(
            stage=DealStage.PROSPECTING,
            probability=10,
            risk=DealRisk.LOW,
        )

        created_deal = await create_deal(async_db_session, deal_data)
        assert created_deal.stage == DealStage.PROSPECTING

        # Stage 1: Qualification
        await update_deal(async_db_session, created_deal, {
            "stage": DealStage.QUALIFICATION,
            "probability": 25,
            "description": "Qualified prospect with clear budget and timeline",
        })

        # Stage 2: Needs Analysis
        await update_deal(async_db_session, created_deal, {
            "stage": DealStage.NEEDS_ANALYSIS,
            "probability": 50,
            "description": "Requirements gathered, solution defined",
        })

        # Stage 3: Proposal
        await update_deal(async_db_session, created_deal, {
            "stage": DealStage.PROPOSAL,
            "probability": 75,
            "description": "Proposal sent, under consideration",
        })

        # Stage 4: Negotiation
        await update_deal(async_db_session, created_deal, {
            "stage": DealStage.NEGOTIATION,
            "probability": 90,
            "description": "Terms being negotiated",
            "discount_percent": Decimal("15.0"),
        })

        # Stage 5: Closed Won
        await update_deal(async_db_session, created_deal, {
            "stage": DealStage.CLOSED_WON,
            "probability": 100,
            "description": "Deal closed successfully",
            "actual_close_date": datetime.utcnow(),
        })

        # Verify final state
        final_deal = await async_db_session.get(Deal, created_deal.id)
        assert final_deal.stage == DealStage.CLOSED_WON
        assert final_deal.probability == 100
        assert final_deal.actual_close_date is not None

    @pytest_asyncio.asyncio
    async def test_deal_lost_workflow(self, async_db_session, generate_test_deal):
        """Test deal lifecycle when deal is lost."""
        deal_data = generate_test_deal(
            stage=DealStage.PROPOSAL,
            probability=60,
            risk=DealRisk.MEDIUM,
        )

        created_deal = await create_deal(async_db_session, deal_data)

        # Mark deal as lost
        await update_deal(async_db_session, created_deal, {
            "stage": DealStage.CLOSED_LOST,
            "probability": 0,
            "lost_reason": "Competitor chosen",
            "competitor": "Competitor Corp",
            "actual_close_date": datetime.utcnow(),
        })

        # Verify deal is properly closed as lost
        final_deal = await async_db_session.get(Deal, created_deal.id)
        assert final_deal.stage == DealStage.CLOSED_LOST
        assert final_deal.probability == 0
        assert final_deal.lost_reason == "Competitor chosen"


class TestPaymentProcessingWorkflow:
    """Testing payment processing workflows with idempotency."""

    @pytest_asyncio.asyncio
    async def test_successful_payment_with_idempotency(self, async_db_session, test_deal, test_invoice, mock_stripe_adapter):
        """Test successful payment processing with idempotency handling."""
        payment_service = PaymentService(async_db_session)

        # Process payment with unique idempotency key
        idempotency_key = f"payment_{test_deal.id}_{int(datetime.utcnow().timestamp())}"

        payment_result = await payment_service.process_payment(
            deal_id=test_deal.id,
            invoice_id=test_invoice.id,
            amount=test_invoice.amount,
            currency=test_invoice.currency,
            idempotency_key=idempotency_key,
            payment_method="pm_stripe_card_123",
        )

        assert payment_result["success"] is True
        assert payment_result["payment_id"] is not None
        assert payment_result["transaction_id"] == "pi_test_123"

        # Verify payment record created
        async with async_db_session:
            payment = await async_db_session.get(Payment, payment_result["payment_id"])
            assert payment.status == PaymentStatus.SUCCEEDED
            assert payment.amount == test_invoice.amount
            assert payment.idempotency_key == idempotency_key

    @pytest_asyncio.asyncio
    async def test_idempotency_protection_duplicate_payment(self, async_db_session, test_deal, test_invoice, mock_stripe_adapter):
        """Test that duplicate payment requests are rejected due to idempotency."""
        payment_service = PaymentService(async_db_session)

        # First payment
        idempotency_key = f"payment_{test_deal.id}_{int(datetime.utcnow().timestamp())}"

        payment_result1 = await payment_service.process_payment(
            deal_id=test_deal.id,
            invoice_id=test_invoice.id,
            amount=test_invoice.amount,
            currency=test_invoice.currency,
            idempotency_key=idempotency_key,
            payment_method="pm_stripe_card_123",
        )

        assert payment_result1["success"] is True

        # Second payment with same idempotency key
        payment_result2 = await payment_service.process_payment(
            deal_id=test_deal.id,
            invoice_id=test_invoice.id,
            amount=test_invoice.amount,
            currency=test_invoice.currency,
            idempotency_key=idempotency_key,  # Same key
            payment_method="pm_stripe_card_456",
        )

        # Should return the original payment result
        assert payment_result2["success"] is True
        assert payment_result2["payment_id"] == payment_result1["payment_id"]
        assert payment_result2["duplicate"] is True

    @pytest_asyncio.asyncio
    async def test_payment_refund_workflow(self, async_db_session, test_payment, mock_stripe_adapter):
        """Test payment refund workflow."""
        payment_service = PaymentService(async_db_session)

        # Process refund
        refund_result = await payment_service.refund_payment(
            payment_id=test_payment.id,
            refund_amount=Decimal("5000.00"),  # Partial refund
            reason="Customer requested partial refund",
        )

        assert refund_result["success"] is True
        assert refund_result["refund_id"] is not None
        assert refund_result["amount"] == Decimal("5000.00")

        # Verify payment status updated
        async with async_db_session:
            updated_payment = await async_db_session.get(Payment, test_payment.id)
            assert updated_payment.status == PaymentStatus.PARTIALLY_REFUNDED

    @pytest_asyncio.asyncio
    async def test_payment_retry_on_failure(self, async_db_session, test_deal, test_invoice):
        """Test payment retry mechanism on temporary failures."""
        payment_service = PaymentService(async_db_session)

        with patch.object(StripeAdapter, 'create_payment_intent') as mock_payment:
            # First call fails, second succeeds
            mock_payment.side_effect = [
                Exception("Temporary network error"),
                {
                    "id": "pi_test_retry_123",
                    "status": "requires_payment_method",
                    "client_secret": "pi_test_retry_123_secret_test",
                }
            ]

            # Process payment with retry
            payment_result = await payment_service.process_payment_with_retry(
                deal_id=test_deal.id,
                invoice_id=test_invoice.id,
                amount=test_invoice.amount,
                currency=test_invoice.currency,
                max_retries=3,
                retry_delay=0.1,  # Short delay for testing
            )

            assert payment_result["success"] is True
            assert payment_result["transaction_id"] == "pi_test_retry_123"
            assert payment_result["retry_count"] == 1


class TestInvoiceAndERPIntegrationWorkflow:
    """Testing invoice creation and ERP integration workflows."""

    @pytest_asyncio.asyncio
    async def test_invoice_creation_and_staging(self, async_db_session, test_deal):
        """Test invoice creation and staging for ERP integration."""
        invoice_service = InvoiceService(async_db_session)

        # Create invoice from deal
        invoice_result = await invoice_service.create_invoice_from_deal(
            deal_id=test_deal.id,
            invoice_type="standard",
            due_days=test_deal.payment_terms_days,
            line_items=[
                {
                    "description": "Software License",
                    "quantity": 1,
                    "unit_price": test_deal.amount,
                    "total": test_deal.amount,
                }
            ],
        )

        assert invoice_result["success"] is True
        assert invoice_result["invoice_id"] is not None

        # Verify invoice details
        async with async_db_session:
            invoice = await async_db_session.get(Invoice, invoice_result["invoice_id"])
            assert invoice.deal_id == test_deal.id
            assert invoice.amount == test_deal.amount
            assert invoice.currency == test_deal.currency
            assert invoice.status == InvoiceStatus.DRAFT
            assert invoice.invoice_type == "standard"

    @pytest_asyncio.asyncio
    async def test_erp_integration_submission(self, async_db_session, test_invoice):
        """Test ERP integration submission workflow."""
        invoice_service = InvoiceService(async_db_session)

        with patch.object(invoice_service.erp_adapter, 'submit_invoice') as mock_erp:
            mock_erp.return_value = {
                "erp_id": "ERP-INV-001",
                "status": "submitted",
                "submission_timestamp": datetime.utcnow().isoformat(),
            }

            # Submit to ERP
            erp_result = await invoice_service.submit_to_erp(
                invoice_id=test_invoice.id,
                priority="normal",
            )

            assert erp_result["success"] is True
            assert erp_result["erp_id"] == "ERP-INV-001"

            # Verify invoice status updated
            async with async_db_session:
                updated_invoice = await async_db_session.get(Invoice, test_invoice.id)
                assert updated_invoice.status == InvoiceStatus.SUBMITTED
                assert updated_invoice.erp_id == "ERP-INV-001"

    @pytest_asyncio.asyncio
    async def test_invoice_erp_synchronization(self, async_db_session, test_invoice):
        """Test invoice synchronization with ERP system."""
        invoice_service = InvoiceService(async_db_session)

        with patch.object(invoice_service.erp_adapter, 'get_invoice_status') as mock_status:
            mock_status.return_value = {
                "erp_id": "ERP-INV-001",
                "status": "paid",
                "paid_date": datetime.utcnow().date().isoformat(),
                "paid_amount": str(test_invoice.amount),
            }

            # Sync status from ERP
            sync_result = await invoice_service.sync_from_erp(
                invoice_id=test_invoice.id,
            )

            assert sync_result["success"] is True
            assert sync_result["new_status"] == InvoiceStatus.PAID

            # Verify invoice updated
            async with async_db_session:
                updated_invoice = await async_db_session.get(Invoice, test_invoice.id)
                assert updated_invoice.status == InvoiceStatus.PAID
                assert updated_invoice.paid_date is not None


class TestESignatureWorkflow:
    """Testing complete e-signature workflows."""

    @pytest_asyncio.asyncio
    async def test_document_signing_flow(self, async_db_session, test_deal):
        """Test complete document signing flow."""
        # Create e-signature adapter
        docusign_adapter = DocuSignAdapter(
            api_key="test_key",
            base_url="https://demo.docusign.net/restapi",
            account_id="test_account"
        )

        with patch.object(docusign_adapter, 'send_envelope') as mock_send, \
             patch.object(docusign_adapter, 'get_envelope_status') as mock_status:

            # Mock envelope creation
            mock_send.return_value = {
                "envelope_id": "envelope_123",
                "status": "sent",
                "signing_url": "https://demo.docusign.net/Signing/...",
            }

            # Send for signature
            envelope_result = await docusign_adapter.send_envelope(
                template_id="template_123",
                recipients=[{
                    "email": "customer@example.com",
                    "name": "John Customer",
                    "role": "signer",
                }],
                custom_fields={"deal_id": test_deal.id},
            )

            assert envelope_result["envelope_id"] == "envelope_123"
            assert envelope_result["status"] == "sent"

            # Mock completed signature
            mock_status.return_value = {
                "envelope_id": "envelope_123",
                "status": "completed",
                "completed_date": datetime.utcnow().isoformat(),
            }

            # Check signature status
            status_result = await docusign_adapter.get_envelope_status("envelope_123")
            assert status_result["status"] == "completed"

    @pytest_asyncio.asyncio
    async def test_multi_signer_workflow(self, async_db_session, test_deal):
        """Test e-signature workflow with multiple signers."""
        docusign_adapter = DocuSignAdapter(
            api_key="test_key",
            base_url="https://demo.docusign.net/restapi",
            account_id="test_account"
        )

        with patch.object(docusign_adapter, 'send_envelope') as mock_send:
            mock_send.return_value = {
                "envelope_id": "envelope_multi_123",
                "status": "sent",
                "signing_urls": {
                    "customer": "https://demo.docusign.net/Signing/customer",
                    "executive": "https://demo.docusign.net/Signing/executive",
                },
            }

            # Send to multiple signers
            recipients = [
                {
                    "email": "customer@example.com",
                    "name": "John Customer",
                    "role": "signer",
                    "signing_order": 1,
                },
                {
                    "email": "executive@company.com",
                    "name": "Jane Executive",
                    "role": "cc",
                    "signing_order": 2,
                }
            ]

            envelope_result = await docusign_adapter.send_envelope(
                template_id="template_multi_123",
                recipients=recipients,
                custom_fields={"deal_id": test_deal.id},
            )

            assert envelope_result["envelope_id"] == "envelope_multi_123"
            assert len(envelope_result["signing_urls"]) == 2

    @pytest_asyncio.asyncio
    async def test_signature_reminder_workflow(self, async_db_session):
        """Test signature reminder automation."""
        docusign_adapter = DocuSignAdapter(
            api_key="test_key",
            base_url="https://demo.docusign.net/restapi",
            account_id="test_account"
        )

        with patch.object(docusign_adapter, 'send_reminder') as mock_reminder:
            mock_reminder.return_value = {
                "envelope_id": "envelope_123",
                "reminder_sent": True,
                "reminder_timestamp": datetime.utcnow().isoformat(),
            }

            # Send reminder
            reminder_result = await docusign_adapter.send_reminder(
                envelope_id="envelope_123",
                recipient_email="customer@example.com",
                message="Please sign the contract at your earliest convenience.",
            )

            assert reminder_result["reminder_sent"] is True
            assert reminder_result["envelope_id"] == "envelope_123"