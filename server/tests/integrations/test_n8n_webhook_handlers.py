"""
n8n Webhook Handler Integration Tests

Test suite for n8n webhook handlers that provide bidirectional
communication between Deal Desk OS and n8n workflows.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, List
from unittest.mock import AsyncMock, Mock, patch

from app.integrations.n8n.base import (
    N8nEventType,
    WebhookEvent as N8nWebhookEvent,
    WorkflowTrigger,
    WebhookHandler,
    WebhookError,
)
from app.integrations.n8n.handlers import (
    DealWorkflowHandler,
    PaymentWorkflowHandler,
    ESignatureWorkflowHandler,
    ApprovalWorkflowHandler,
)
from app.models.deal import Deal, DealStage, DealRisk, GuardrailStatus
from app.models.payment import Payment, PaymentStatus
from app.models.approval import Approval, ApprovalStatus


class TestN8nWebhookHandlerContract:
    """Contract tests for all n8n webhook handlers."""

    @pytest.mark.asyncio
    async def test_webhook_handler_interface_compliance(self):
        """Test that all webhook handlers implement the required interface."""
        required_methods = [
            'handle_webhook', 'verify_signature', 'parse_event',
            'validate_payload', 'send_webhook', 'health_check'
        ]

        for handler_class in [
            DealWorkflowHandler,
            PaymentWorkflowHandler,
            ESignatureWorkflowHandler,
            ApprovalWorkflowHandler
        ]:
            # Initialize with minimal config
            handler = handler_class(webhook_url="https://test.webhook.url")

            for method_name in required_methods:
                assert hasattr(handler, method_name), f"{handler_class.__name__} missing {method_name}"
                assert callable(getattr(handler, method_name)), f"{handler_class.__name__}.{method_name} not callable"


class TestDealWorkflowHandler:
    """Test n8n deal workflow webhook handler."""

    @pytest.fixture
    def n8n_config(self):
        return {
            "webhook_url": "https://n8n.example.com/webhook/deal-workflow",
            "api_key": "n8n_api_key_12345",
            "workflow_id": "deal_workflow_123",
            "signature_secret": "n8n_signature_secret"
        }

    @pytest.fixture
    def deal_handler(self, n8n_config):
        return DealWorkflowHandler(**n8n_config)

    @pytest.fixture
    def sample_deal(self):
        return Deal(
            id="deal_12345",
            name="Enterprise Software License",
            amount=Decimal("50000.00"),
            currency="USD",
            stage=DealStage.PRICING,
            risk=DealRisk.MEDIUM,
            probability=75,
            industry="technology",
            owner_id="user_123",
            discount_percent=Decimal("15.0"),
            payment_terms_days=30,
            guardrail_status=GuardrailStatus.PASSED,
            quote_generated_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )

    @pytest.mark.asyncio
    async def test_handle_deal_created_webhook(self, deal_handler, sample_deal):
        """Test handling deal creation webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.DEAL_CREATED,
            "data": {
                "deal_id": sample_deal.id,
                "deal_name": sample_deal.name,
                "amount": float(sample_deal.amount),
                "currency": sample_deal.currency,
                "stage": sample_deal.stage,
                "risk": sample_deal.risk,
                "probability": sample_deal.probability,
                "industry": sample_deal.industry,
                "owner_id": sample_deal.owner_id,
                "discount_percent": float(sample_deal.discount_percent),
                "payment_terms_days": sample_deal.payment_terms_days,
                "guardrail_status": sample_deal.guardrail_status,
                "quote_generated_at": sample_deal.quote_generated_at.isoformat()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Mock n8n API call
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await deal_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.DEAL_CREATED
            assert result.deal_id == sample_deal.id

            # Verify n8n was called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "json" in call_args
            assert call_args["json"]["event"] == "deal.created"

    @pytest.mark.asyncio
    async def test_handle_stage_change_webhook(self, deal_handler, sample_deal):
        """Test handling deal stage change webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.DEAL_STAGE_CHANGED,
            "data": {
                "deal_id": sample_deal.id,
                "old_stage": DealStage.PRICING,
                "new_stage": DealStage.GUARDRAIL_REVIEW,
                "changed_at": datetime.now(timezone.utc).isoformat(),
                "changed_by": "user_123"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await deal_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.DEAL_STAGE_CHANGED

    @pytest.mark.asyncio
    async def test_handle_guardrail_violation_webhook(self, deal_handler, sample_deal):
        """Test handling guardrail violation webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.GUARDRAIL_VIOLATED,
            "data": {
                "deal_id": sample_deal.id,
                "violations": [
                    {
                        "type": "discount_exceeded",
                        "rule": "max_discount_medium_risk",
                        "value": float(sample_deal.discount_percent),
                        "limit": 20.0,
                        "severity": "high"
                    }
                ],
                "escalation_required": True,
                "detected_at": datetime.now(timezone.utc).isoformat()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await deal_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.GUARDRAIL_VIOLATED
            assert "violations" in result.metadata

    @pytest.mark.asyncio
    async def test_verify_webhook_signature(self, deal_handler):
        """Test webhook signature verification."""
        payload = b'{"event": "deal.created", "data": {"deal_id": "deal_123"}}'
        signature = "test_signature"

        # Mock signature verification
        with patch('hmac.compare_digest') as mock_compare:
            mock_compare.return_value = True

            is_valid = await deal_handler.verify_signature(payload, signature)

            assert is_valid is True
            mock_compare.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_payload_structure(self, deal_handler):
        """Test webhook payload validation."""
        # Valid payload
        valid_payload = {
            "event": N8nWebhookEvent.DEAL_CREATED,
            "data": {"deal_id": "deal_123"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        result = await deal_handler.validate_payload(valid_payload)
        assert result is True

        # Invalid payload - missing event
        invalid_payload = {
            "data": {"deal_id": "deal_123"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        result = await deal_handler.validate_payload(invalid_payload)
        assert result is False

        # Invalid payload - missing data
        invalid_payload2 = {
            "event": N8nWebhookEvent.DEAL_CREATED,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        result = await deal_handler.validate_payload(invalid_payload2)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_to_n8n(self, deal_handler, sample_deal):
        """Test sending webhook to n8n."""
        event_type = N8nWebhookEvent.DEAL_COMPLETED
        event_data = {
            "deal_id": sample_deal.id,
            "completion_reason": "payment_collected",
            "total_amount": float(sample_deal.amount),
            "completion_time": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={
                "workflow_execution_id": "exec_12345",
                "status": "success"
            })

            result = await deal_handler.send_webhook(event_type, event_data)

            assert result.success is True
            assert result.execution_id == "exec_12345"
            assert "workflow_execution_id" in result.metadata

            # Verify the call was made correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == deal_handler.webhook_url
            assert call_args[1]["json"]["event"] == event_type
            assert call_args[1]["json"]["data"] == event_data

    @pytest.mark.asyncio
    async def test_webhook_retry_logic(self, deal_handler, sample_deal):
        """Test webhook retry logic on failures."""
        webhook_payload = {
            "event": N8nWebhookEvent.DEAL_CREATED,
            "data": {"deal_id": sample_deal.id},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Mock failing n8n API
        with patch('aiohttp.ClientSession.post') as mock_post:
            # First call fails, second succeeds
            mock_post.return_value.__aenter__.return_value.status = 500
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"error": "Server error"})

            with pytest.raises(WebhookError) as exc_info:
                await deal_handler.handle_webhook(webhook_payload)

            assert "Failed to send webhook" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_health_check(self, deal_handler):
        """Test handler health check."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
                "status": "healthy",
                "workflow_id": deal_handler.config["workflow_id"]
            })

            result = await deal_handler.health_check()

            assert result is True
            mock_get.assert_called_once()


class TestPaymentWorkflowHandler:
    """Test n8n payment workflow webhook handler."""

    @pytest.fixture
    def payment_handler(self):
        return PaymentWorkflowHandler(
            webhook_url="https://n8n.example.com/webhook/payment-workflow",
            api_key="n8n_api_key_12345",
            workflow_id="payment_workflow_123"
        )

    @pytest.fixture
    def sample_payment(self):
        return Payment(
            id="payment_12345",
            deal_id="deal_123",
            status=PaymentStatus.SUCCEEDED,
            amount=Decimal("50000.00"),
            currency="USD",
            idempotency_key="payment_idemp_123",
            provider_reference="stripe_pi_12345",
            attempt_number=1,
            completed_at=datetime.now(timezone.utc)
        )

    @pytest.mark.asyncio
    async def test_handle_payment_succeeded_webhook(self, payment_handler, sample_payment):
        """Test handling payment success webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.PAYMENT_SUCCEEDED,
            "data": {
                "payment_id": sample_payment.id,
                "deal_id": sample_payment.deal_id,
                "amount": float(sample_payment.amount),
                "currency": sample_payment.currency,
                "provider_reference": sample_payment.provider_reference,
                "attempt_number": sample_payment.attempt_number,
                "completed_at": sample_payment.completed_at.isoformat()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await payment_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.PAYMENT_SUCCEEDED
            assert result.payment_id == sample_payment.id

    @pytest.mark.asyncio
    async def test_handle_payment_failed_webhook(self, payment_handler, sample_payment):
        """Test handling payment failure webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.PAYMENT_FAILED,
            "data": {
                "payment_id": sample_payment.id,
                "deal_id": sample_payment.deal_id,
                "amount": float(sample_payment.amount),
                "currency": sample_payment.currency,
                "failure_reason": "insufficient_funds",
                "error_code": "card_declined",
                "attempt_number": sample_payment.attempt_number,
                "retry_possible": True,
                "next_retry_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await payment_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.PAYMENT_FAILED
            assert result.metadata["failure_reason"] == "insufficient_funds"


class TestESignatureWorkflowHandler:
    """Test n8n e-signature workflow webhook handler."""

    @pytest.fixture
    def esignature_handler(self):
        return ESignatureWorkflowHandler(
            webhook_url="https://n8n.example.com/webhook/esignature-workflow",
            api_key="n8n_api_key_12345",
            workflow_id="esignature_workflow_123"
        )

    @pytest.mark.asyncio
    async def test_handle_agreement_signed_webhook(self, esignature_handler):
        """Test handling agreement signed webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.AGREEMENT_SIGNED,
            "data": {
                "envelope_id": "envelope_12345",
                "deal_id": "deal_123",
                "signers": [
                    {
                        "name": "John Doe",
                        "email": "john@example.com",
                        "signed_at": datetime.now(timezone.utc).isoformat()
                    }
                ],
                "documents_signed": 2,
                "completion_time": datetime.now(timezone.utc).isoformat()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await esignature_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.AGREEMENT_SIGNED
            assert result.envelope_id == "envelope_12345"


class TestApprovalWorkflowHandler:
    """Test n8n approval workflow webhook handler."""

    @pytest.fixture
    def approval_handler(self):
        return ApprovalWorkflowHandler(
            webhook_url="https://n8n.example.com/webhook/approval-workflow",
            api_key="n8n_api_key_12345",
            workflow_id="approval_workflow_123"
        )

    @pytest.fixture
    def sample_approval(self):
        return Approval(
            id="approval_12345",
            deal_id="deal_123",
            stage="finance",
            status=ApprovalStatus.APPROVED,
            approver_id="user_456",
            approver_name="Finance Manager",
            order=2,
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
            completed_at=datetime.now(timezone.utc)
        )

    @pytest.mark.asyncio
    async def test_handle_approval_completed_webhook(self, approval_handler, sample_approval):
        """Test handling approval completed webhook."""
        webhook_payload = {
            "event": N8nWebhookEvent.APPROVAL_COMPLETED,
            "data": {
                "approval_id": sample_approval.id,
                "deal_id": sample_approval.deal_id,
                "stage": sample_approval.stage,
                "status": sample_approval.status,
                "approver_id": sample_approval.approver_id,
                "approver_name": sample_approval.approver_name,
                "order": sample_approval.order,
                "completed_at": sample_approval.completed_at.isoformat(),
                "comments": "Approved with standard terms",
                "next_stage": "legal"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value={"status": "success"})

            result = await approval_handler.handle_webhook(webhook_payload)

            assert result.success is True
            assert result.event_type == N8nWebhookEvent.APPROVAL_COMPLETED
            assert result.approval_id == sample_approval.id


class TestN8nWorkflowIntegration:
    """Integration tests for n8n workflow handlers."""

    @pytest.mark.asyncio
    async def test_end_to_end_deal_workflow(self):
        """Test complete deal workflow through n8n."""
        # This will test the complete lifecycle:
        # Deal Created -> Stage Changes -> Guardrail Check -> Approval -> E-signature -> Payment
        pass

    @pytest.mark.asyncio
    async def test_concurrent_workflow_handling(self):
        """Test handling multiple concurrent workflows."""
        # Test concurrent webhook processing
        pass

    @pytest.mark.asyncio
    async def test_workflow_error_recovery(self):
        """Test workflow error handling and recovery."""
        # Test retry logic and error handling
        pass

    @pytest.mark.asyncio
    async def test_workflow_ordering_and_sequencing(self):
        """Test proper workflow ordering and sequencing."""
        # Ensure workflows execute in correct order
        pass


class TestN8nCompliance:
    """Test n8n workflow compliance and security features."""

    @pytest.mark.asyncio
    async def test_webhook_auditing(self):
        """Test comprehensive webhook auditing."""
        # Ensure all webhook communications are logged
        pass

    @pytest.mark.asyncio
    async def test_webhook_security(self):
        """Test webhook security and authentication."""
        # Test signature verification and access control
        pass

    @pytest.mark.asyncio
    async def test_data_privacy_compliance(self):
        """Test data privacy compliance for webhook data."""
        # Ensure sensitive data is handled properly
        pass