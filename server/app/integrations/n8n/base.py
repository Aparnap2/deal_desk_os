"""
n8n Integration Base Classes and Interfaces

Defines the contract and base functionality for n8n workflow integration
in the Deal Desk OS system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


class N8nEventType(str, Enum):
    """n8n webhook event types."""
    # Deal events
    DEAL_CREATED = "deal.created"
    DEAL_UPDATED = "deal.updated"
    DEAL_STAGE_CHANGED = "deal.stage_changed"
    DEAL_COMPLETED = "deal.completed"
    DEAL_CANCELLED = "deal.cancelled"

    # Guardrail events
    GUARDRAIL_PASSED = "guardrail.passed"
    GUARDRAIL_VIOLATED = "guardrail.violated"
    GUARDRAIL_ESCALATED = "guardrail.escalated"

    # Approval events
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_STARTED = "approval.started"
    APPROVAL_COMPLETED = "approval.completed"
    APPROVAL_DECLINED = "approval.declined"
    APPROVAL_ESCALATED = "approval.escalated"

    # E-signature events
    AGREEMENT_CREATED = "agreement.created"
    AGREEMENT_SENT = "agreement.sent"
    AGREEMENT_SIGNED = "agreement.signed"
    AGREEMENT_DECLINED = "agreement.declined"
    AGREEMENT_COMPLETED = "agreement.completed"

    # Payment events
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_PROCESSING = "payment.processing"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_ROLLBACK = "payment.rollback"
    PAYMENT_REFUNDED = "payment.refunded"

    # System events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"


class WebhookEvent(str, Enum):
    """Webhook event types for external integrations."""
    # Legacy support - map to N8nEventType
    DEAL_CREATED = N8nEventType.DEAL_CREATED
    DEAL_STAGE_CHANGED = N8nEventType.DEAL_STAGE_CHANGED
    GUARDRAIL_VIOLATED = N8nEventType.GUARDRAIL_VIOLATED
    APPROVAL_COMPLETED = N8nEventType.APPROVAL_COMPLETED
    AGREEMENT_SIGNED = N8nEventType.AGREEMENT_SIGNED
    PAYMENT_SUCCEEDED = N8nEventType.PAYMENT_SUCCEEDED
    PAYMENT_FAILED = N8nEventType.PAYMENT_FAILED


class WorkflowTrigger(str, Enum):
    """Workflow trigger types."""
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    EVENT = "event"


class WebhookStatus(str, Enum):
    """Webhook processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"


@dataclass
class WorkflowConfig:
    """n8n workflow configuration."""
    workflow_id: str
    webhook_url: str
    api_key: Optional[str] = None
    signature_secret: Optional[str] = None
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: int = 5
    enabled: bool = True
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class WebhookPayload:
    """Webhook payload structure."""
    event: WebhookEvent
    data: Dict[str, Any]
    timestamp: datetime
    correlation_id: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class WebhookResult:
    """Result of webhook processing."""
    success: bool
    event_type: WebhookEvent
    webhook_url: str
    status: WebhookStatus
    processed_at: datetime
    execution_id: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    attempt_number: int = 1
    metadata: Optional[Dict[str, Any]] = None

    # Entity-specific IDs (extracted from payload for easy access)
    deal_id: Optional[str] = None
    payment_id: Optional[str] = None
    approval_id: Optional[str] = None
    envelope_id: Optional[str] = None


@dataclass
class WorkflowExecution:
    """n8n workflow execution information."""
    execution_id: str
    workflow_id: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class WebhookError(Exception):
    """Webhook processing specific errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        webhook_url: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.error_message = message
        self.error_code = error_code
        self.status_code = status_code
        self.webhook_url = webhook_url
        self.payload = payload
        self.response_data = response_data


class WebhookHandler(ABC):
    """Abstract base class for webhook handlers."""

    def __init__(self, **config):
        """Initialize the webhook handler with configuration."""
        self.config = config
        self.webhook_url = config.get("webhook_url", "")
        self.api_key = config.get("api_key")
        self.signature_secret = config.get("signature_secret")
        self.timeout_seconds = config.get("timeout_seconds", 30)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.retry_delay_seconds = config.get("retry_delay_seconds", 5)

    @abstractmethod
    async def handle_webhook(self, payload: Dict[str, Any]) -> WebhookResult:
        """
        Handle incoming webhook payload.

        Args:
            payload: Webhook payload data

        Returns:
            WebhookResult with processing details

        Raises:
            WebhookError: If webhook processing fails
        """
        pass

    @abstractmethod
    async def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature for security.

        Args:
            payload: Raw webhook payload bytes
            signature: Webhook signature

        Returns:
            True if signature is valid

        Raises:
            WebhookError: If signature verification fails
        """
        pass

    @abstractmethod
    async def parse_event(self, payload: Dict[str, Any]) -> WebhookPayload:
        """
        Parse webhook payload into structured event.

        Args:
            payload: Raw webhook payload

        Returns:
            Parsed WebhookPayload

        Raises:
            WebhookError: If parsing fails
        """
        pass

    async def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """
        Validate webhook payload structure.

        Args:
            payload: Webhook payload to validate

        Returns:
            True if payload is valid
        """
        required_fields = ["event", "data", "timestamp"]
        return all(field in payload for field in required_fields)

    async def send_webhook(
        self,
        event_type: WebhookEvent,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> WebhookResult:
        """
        Send webhook to n8n workflow.

        Args:
            event_type: Type of event to send
            data: Event data
            correlation_id: Correlation ID for tracking
            **kwargs: Additional parameters

        Returns:
            WebhookResult with send details

        Raises:
            WebhookError: If sending fails
        """
        from aiohttp import ClientSession, ClientTimeout
        import asyncio
        import hmac
        hashlib

        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "correlation_id": correlation_id,
            "source": "deal_desk_os"
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DealDeskOS/1.0"
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Add signature if secret is configured
        if self.signature_secret:
            payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
            signature = hmac.new(
                self.signature_secret.encode('utf-8'),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = signature

        last_exception = None

        for attempt in range(self.retry_attempts):
            try:
                timeout = ClientTimeout(total=self.timeout_seconds)

                async with ClientSession(timeout=timeout) as session:
                    async with session.post(
                        self.webhook_url,
                        json=payload,
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            response_data = await response.json()

                            return WebhookResult(
                                success=True,
                                event_type=event_type,
                                webhook_url=self.webhook_url,
                                status=WebhookStatus.COMPLETED,
                                processed_at=datetime.now(),
                                execution_id=response_data.get("execution_id"),
                                response_data=response_data,
                                attempt_number=attempt + 1,
                                correlation_id=correlation_id,
                                **self._extract_entity_ids(data)
                            )
                        else:
                            error_text = await response.text()
                            raise WebhookError(
                                message=f"HTTP {response.status}: {error_text}",
                                error_code=f"http_{response.status}",
                                status_code=response.status,
                                webhook_url=self.webhook_url,
                                payload=payload
                            )

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Webhook send attempt {attempt + 1} failed for {event_type}: {e}"
                )

                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay_seconds * (2 ** attempt))  # Exponential backoff
                else:
                    # Final attempt failed
                    raise WebhookError(
                        message=f"Failed to send webhook after {self.retry_attempts} attempts: {str(e)}",
                        error_code="webhook_send_failed",
                        webhook_url=self.webhook_url,
                        payload=payload,
                        response_data={"last_error": str(e)}
                    )

    async def health_check(self) -> bool:
        """
        Check if webhook handler is healthy.

        Returns:
            True if handler is responding correctly

        Raises:
            WebhookError: If health check fails
        """
        # Default implementation - override in subclasses
        return True

    def _extract_entity_ids(self, data: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """Extract common entity IDs from event data."""
        return {
            "deal_id": data.get("deal_id"),
            "payment_id": data.get("payment_id"),
            "approval_id": data.get("approval_id"),
            "envelope_id": data.get("envelope_id")
        }

    def _create_error_result(
        self,
        event_type: WebhookEvent,
        error_message: str,
        error_code: Optional[str] = None,
        attempt_number: int = 1,
        **kwargs
    ) -> WebhookResult:
        """Create a standardized error result."""
        return WebhookResult(
            success=False,
            event_type=event_type,
            webhook_url=self.webhook_url,
            status=WebhookStatus.FAILED,
            processed_at=datetime.now(),
            error_message=error_message,
            error_code=error_code,
            attempt_number=attempt_number,
            **kwargs
        )


class WorkflowHandlerRegistry:
    """Registry for workflow handlers."""

    _handlers: Dict[str, WebhookHandler] = {}

    @classmethod
    def register(cls, name: str, handler: WebhookHandler):
        """Register a workflow handler."""
        cls._handlers[name] = handler

    @classmethod
    def get(cls, name: str) -> Optional[WebhookHandler]:
        """Get a registered handler."""
        return cls._handlers.get(name)

    @classmethod
    def list_handlers(cls) -> List[str]:
        """List all registered handler names."""
        return list(cls._handlers.keys())

    @classmethod
    def unregister(cls, name: str):
        """Unregister a handler."""
        if name in cls._handlers:
            del cls._handlers[name]