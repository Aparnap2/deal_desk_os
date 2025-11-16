"""
n8n integration modules

Provides adapters and handlers for n8n workflow automation
with bidirectional communication and comprehensive error handling.
"""

from .base import (
    WebhookHandler,
    WorkflowHandlerRegistry,
    N8nEventType,
    WebhookEvent,
    WorkflowTrigger,
    WebhookStatus,
    WorkflowConfig,
    WebhookPayload,
    WebhookResult,
    WorkflowExecution,
    WebhookError,
)
from .adapter import N8nWorkflowAdapter

__all__ = [
    "WebhookHandler",
    "WorkflowHandlerRegistry",
    "N8nEventType",
    "WebhookEvent",
    "WorkflowTrigger",
    "WebhookStatus",
    "WorkflowConfig",
    "WebhookPayload",
    "WebhookResult",
    "WorkflowExecution",
    "WebhookError",
    "N8nWorkflowAdapter",
]