from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class WorkflowEventType(str, Enum):
    """Supported workflow event types."""
    DEAL_CREATED = "deal.created"
    DEAL_UPDATED = "deal.updated"
    DEAL_STAGE_CHANGED = "deal.stage_changed"
    PAYMENT_SUCCESS = "payment.success"
    PAYMENT_FAILED = "payment.failed"
    DOCUMENT_SIGNED = "document.signed"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"
    GUARDRAIL_VIOLATION = "guardrail.violation"
    QUOTE_GENERATED = "quote.generated"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class WorkflowEvent:
    """Represents a workflow event with context data."""
    event_type: WorkflowEventType
    entity_id: str
    entity_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_type": self.event_type.value,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class WorkflowResult:
    """Represents the result of a workflow execution."""
    workflow_id: str
    status: WorkflowStatus
    event_type: WorkflowEventType
    entity_id: str
    message: str = ""
    output_data: Dict[str, Any] = field(default_factory=dict)
    error_details: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "event_type": self.event_type.value,
            "entity_id": self.entity_id,
            "message": self.message,
            "output_data": self.output_data,
            "error_details": self.error_details,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class WorkflowEngine(ABC):
    """Abstract base class for workflow engines."""

    @abstractmethod
    async def trigger_workflow(
        self,
        event: WorkflowEvent,
    ) -> WorkflowResult:
        """
        Trigger a workflow based on the given event.
        
        Args:
            event: The workflow event to process
            
        Returns:
            WorkflowResult: The result of the workflow execution
        """
        pass

    @abstractmethod
    async def handle_webhook(
        self,
        webhook_type: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> WorkflowResult:
        """
        Handle incoming webhook events.
        
        Args:
            webhook_type: The type of webhook
            payload: The webhook payload
            headers: Optional HTTP headers
            
        Returns:
            WorkflowResult: The result of processing the webhook
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the workflow engine.
        
        Returns:
            Dict containing health status information
        """
        pass

    @abstractmethod
    def get_supported_events(self) -> List[WorkflowEventType]:
        """
        Get the list of supported workflow event types.
        
        Returns:
            List of supported WorkflowEventType values
        """
        pass

    def is_event_supported(self, event_type: WorkflowEventType) -> bool:
        """
        Check if a specific event type is supported.
        
        Args:
            event_type: The event type to check
            
        Returns:
            True if the event type is supported, False otherwise
        """
        return event_type in self.get_supported_events()