"""
n8n Workflow Adapter

Implements the WorkflowEngine interface for n8n integration,
providing a bridge between the workflow abstraction and n8n workflows.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Type
import logging

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.workflow_engine import (
    WorkflowEngine,
    WorkflowEvent,
    WorkflowResult,
    WorkflowEventType,
    WorkflowStatus,
)

from .base import (
    WebhookHandler,
    WebhookEvent,
    WebhookResult,
    WebhookStatus,
    N8nEventType,
    WorkflowHandlerRegistry,
    WebhookError,
)

logger = get_logger(__name__)

# Mapping between WorkflowEventType and N8nEventType
WORKFLOW_TO_N8N_EVENT_MAP = {
    WorkflowEventType.DEAL_CREATED: N8nEventType.DEAL_CREATED,
    WorkflowEventType.DEAL_UPDATED: N8nEventType.DEAL_UPDATED,
    WorkflowEventType.DEAL_STAGE_CHANGED: N8nEventType.DEAL_STAGE_CHANGED,
    WorkflowEventType.PAYMENT_SUCCESS: N8nEventType.PAYMENT_SUCCEEDED,
    WorkflowEventType.PAYMENT_FAILED: N8nEventType.PAYMENT_FAILED,
    WorkflowEventType.DOCUMENT_SIGNED: N8nEventType.AGREEMENT_SIGNED,
    WorkflowEventType.APPROVAL_GRANTED: N8nEventType.APPROVAL_COMPLETED,
    WorkflowEventType.APPROVAL_REJECTED: N8nEventType.APPROVAL_DECLINED,
    WorkflowEventType.GUARDRAIL_VIOLATION: N8nEventType.GUARDRAIL_VIOLATED,
    WorkflowEventType.QUOTE_GENERATED: N8nEventType.DEAL_CREATED,  # Map to deal creation
}

# Reverse mapping for incoming webhooks
N8N_TO_WORKFLOW_EVENT_MAP = {v: k for k, v in WORKFLOW_TO_N8N_EVENT_MAP.items()}


class N8nWorkflowAdapter(WorkflowEngine):
    """
    Adapter for n8n workflow engine that implements the WorkflowEngine interface.
    
    This adapter acts as a bridge between the workflow abstraction layer and
    the n8n integration, handling event conversion and webhook management.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the n8n workflow adapter.
        
        Args:
            config: Optional configuration dictionary (overrides settings)
        """
        self.settings = get_settings()
        self.config = config or {}
        
        # Use config dict if provided, otherwise use settings
        self.enabled = self.config.get("enabled", self.settings.n8n_enabled)
        self.webhook_url = self.config.get("webhook_url", self.settings.n8n_webhook_url or "")
        self.api_key = self.config.get("api_key", self.settings.n8n_api_key)
        self.signature_secret = self.config.get("signature_secret", self.settings.n8n_signature_secret)
        self.timeout_seconds = self.config.get("timeout_seconds", self.settings.n8n_timeout_seconds)
        self.retry_attempts = self.config.get("retry_attempts", self.settings.n8n_retry_attempts)
        self.retry_delay_seconds = self.config.get("retry_delay_seconds", self.settings.n8n_retry_delay_seconds)
        
        # Initialize handlers registry
        self.handler_registry = WorkflowHandlerRegistry()
        
        # Try to load specific handlers if available
        self._load_handlers()
        
        logger.info(f"n8n workflow adapter initialized (enabled: {self.enabled})")

    def _load_handlers(self):
        """
        Load available workflow handlers.
        
        Attempts to import and register specific handlers if they exist.
        If handlers are not available, the adapter will still function with
        basic webhook capabilities.
        """
        try:
            # Try to import handlers module
            from .handlers import (
                DealWorkflowHandler,
                PaymentWorkflowHandler,
                ESignatureWorkflowHandler,
                ApprovalWorkflowHandler,
            )
            
            # Register handlers if they exist
            if self.webhook_url:
                handler_config = {
                    "webhook_url": self.webhook_url,
                    "api_key": self.api_key,
                    "signature_secret": self.signature_secret,
                    "timeout_seconds": self.timeout_seconds,
                    "retry_attempts": self.retry_attempts,
                    "retry_delay_seconds": self.retry_delay_seconds,
                    **self.config
                }
                
                deal_handler = DealWorkflowHandler(**handler_config)
                self.handler_registry.register("deal", deal_handler)
                
                payment_handler = PaymentWorkflowHandler(**handler_config)
                self.handler_registry.register("payment", payment_handler)
                
                esignature_handler = ESignatureWorkflowHandler(**handler_config)
                self.handler_registry.register("esignature", esignature_handler)
                
                approval_handler = ApprovalWorkflowHandler(**handler_config)
                self.handler_registry.register("approval", approval_handler)
                
                logger.info("Loaded specific n8n workflow handlers")
            
        except ImportError as e:
            logger.warning(f"Could not load specific n8n handlers: {e}")
            logger.info("Adapter will function with basic webhook capabilities")

    async def trigger_workflow(self, event: WorkflowEvent) -> WorkflowResult:
        """
        Trigger a workflow based on the given event.
        
        Args:
            event: The workflow event to process
            
        Returns:
            WorkflowResult: The result of the workflow execution
        """
        start_time = datetime.utcnow()
        
        # Check if n8n is enabled
        if not self.enabled:
            return WorkflowResult(
                workflow_id="n8n_disabled",
                status=WorkflowStatus.FAILED,
                event_type=event.event_type,
                entity_id=event.entity_id,
                message="n8n workflow engine is disabled",
                error_details={"reason": "disabled"},
                timestamp=start_time,
            )
        
        # Check if event type is supported
        if not self.is_event_supported(event.event_type):
            return WorkflowResult(
                workflow_id="n8n_unsupported",
                status=WorkflowStatus.FAILED,
                event_type=event.event_type,
                entity_id=event.entity_id,
                message=f"Event type {event.event_type} is not supported",
                error_details={"event_type": event.event_type.value},
                timestamp=start_time,
            )
        
        try:
            # Convert WorkflowEvent to n8n webhook payload
            n8n_event_type = WORKFLOW_TO_N8N_EVENT_MAP.get(event.event_type)
            if not n8n_event_type:
                raise ValueError(f"No mapping for event type: {event.event_type}")
            
            # Get appropriate handler
            handler = self._get_handler_for_event(event.event_type, event.entity_type)
            
            # Prepare webhook data
            webhook_data = {
                "entity_id": event.entity_id,
                "entity_type": event.entity_type,
                "payload": event.payload,
                "user_id": event.user_id,
                "metadata": event.metadata,
                "timestamp": event.timestamp.isoformat(),
            }
            
            # Add entity-specific data from payload
            webhook_data.update(event.payload)
            
            # Send webhook
            if handler:
                # Use specific handler
                webhook_result = await handler.send_webhook(
                    event_type=WebhookEvent(n8n_event_type),
                    data=webhook_data,
                    correlation_id=f"{event.event_type.value}_{event.entity_id}",
                )
            else:
                # Use generic webhook sending
                webhook_result = await self._send_generic_webhook(
                    event_type=WebhookEvent(n8n_event_type),
                    data=webhook_data,
                )
            
            # Convert result
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            if webhook_result.success:
                return WorkflowResult(
                    workflow_id=webhook_result.execution_id or "n8n_workflow",
                    status=WorkflowStatus.COMPLETED,
                    event_type=event.event_type,
                    entity_id=event.entity_id,
                    message="Workflow triggered successfully",
                    output_data=webhook_result.response_data or {},
                    execution_time_ms=execution_time,
                    timestamp=datetime.utcnow(),
                )
            else:
                return WorkflowResult(
                    workflow_id="n8n_failed",
                    status=WorkflowStatus.FAILED,
                    event_type=event.event_type,
                    entity_id=event.entity_id,
                    message=webhook_result.error_message or "Webhook failed",
                    error_details={
                        "error_code": webhook_result.error_code,
                        "webhook_url": webhook_result.webhook_url,
                    },
                    execution_time_ms=execution_time,
                    timestamp=datetime.utcnow(),
                )
                
        except Exception as e:
            logger.error(f"Error triggering n8n workflow: {e}")
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return WorkflowResult(
                workflow_id="n8n_error",
                status=WorkflowStatus.FAILED,
                event_type=event.event_type,
                entity_id=event.entity_id,
                message=f"Error triggering workflow: {str(e)}",
                error_details={"exception": str(e)},
                execution_time_ms=execution_time,
                timestamp=datetime.utcnow(),
            )

    async def handle_webhook(
        self,
        webhook_type: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> WorkflowResult:
        """
        Handle incoming webhook events from n8n.
        
        Args:
            webhook_type: The type of webhook
            payload: The webhook payload
            headers: Optional HTTP headers
            
        Returns:
            WorkflowResult: The result of processing the webhook
        """
        start_time = datetime.utcnow()
        
        # Check if n8n is enabled
        if not self.enabled:
            return WorkflowResult(
                workflow_id="n8n_disabled",
                status=WorkflowStatus.FAILED,
                event_type=WorkflowEventType.DEAL_CREATED,  # Default
                entity_id="unknown",
                message="n8n workflow engine is disabled",
                error_details={"reason": "disabled"},
                timestamp=start_time,
            )
        
        try:
            # Parse the webhook payload
            event_type = payload.get("event")
            data = payload.get("data", {})
            
            if not event_type:
                raise ValueError("Missing event type in webhook payload")
            
            # Convert n8n event to workflow event
            n8n_event = N8nEventType(event_type)
            workflow_event_type = N8N_TO_WORKFLOW_EVENT_MAP.get(n8n_event)
            
            if not workflow_event_type:
                raise ValueError(f"Unsupported n8n event type: {event_type}")
            
            # Extract entity information
            entity_id = data.get("entity_id") or data.get("deal_id") or data.get("payment_id") or "unknown"
            entity_type = data.get("entity_type", "unknown")
            
            # Get appropriate handler for processing
            handler = self._get_handler_for_event(workflow_event_type, entity_type)
            
            if handler:
                # Use specific handler to process webhook
                webhook_result = await handler.handle_webhook(payload)
            else:
                # Generic webhook processing
                webhook_result = await self._process_generic_webhook(payload)
            
            # Convert result
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            if webhook_result.success:
                return WorkflowResult(
                    workflow_id=webhook_result.execution_id or "n8n_webhook",
                    status=WorkflowStatus.COMPLETED,
                    event_type=workflow_event_type,
                    entity_id=entity_id,
                    message="Webhook processed successfully",
                    output_data=webhook_result.response_data or {},
                    execution_time_ms=execution_time,
                    timestamp=datetime.utcnow(),
                )
            else:
                return WorkflowResult(
                    workflow_id="n8n_webhook_failed",
                    status=WorkflowStatus.FAILED,
                    event_type=workflow_event_type,
                    entity_id=entity_id,
                    message=webhook_result.error_message or "Webhook processing failed",
                    error_details={
                        "error_code": webhook_result.error_code,
                        "webhook_url": webhook_result.webhook_url,
                    },
                    execution_time_ms=execution_time,
                    timestamp=datetime.utcnow(),
                )
                
        except Exception as e:
            logger.error(f"Error handling n8n webhook: {e}")
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return WorkflowResult(
                workflow_id="n8n_webhook_error",
                status=WorkflowStatus.FAILED,
                event_type=WorkflowEventType.DEAL_CREATED,  # Default
                entity_id="unknown",
                message=f"Error processing webhook: {str(e)}",
                error_details={"exception": str(e)},
                execution_time_ms=execution_time,
                timestamp=datetime.utcnow(),
            )

    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the n8n workflow engine.
        
        Returns:
            Dict containing health status information
        """
        if not self.enabled:
            return {
                "status": "disabled",
                "message": "n8n workflow engine is disabled",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        try:
            # Check if we have any handlers
            handlers = self.handler_registry.list_handlers()
            
            if not handlers and not self.webhook_url:
                return {
                    "status": "unhealthy",
                    "message": "No handlers configured and no webhook URL",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            
            # Check handler health if available
            if handlers:
                for handler_name in handlers:
                    handler = self.handler_registry.get(handler_name)
                    if handler:
                        is_healthy = await handler.health_check()
                        if not is_healthy:
                            return {
                                "status": "unhealthy",
                                "message": f"Handler {handler_name} is unhealthy",
                                "timestamp": datetime.utcnow().isoformat(),
                            }
            
            return {
                "status": "healthy",
                "message": "n8n workflow engine is operational",
                "handlers": handlers,
                "webhook_url": self.webhook_url,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error during n8n health check: {e}")
            return {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    def get_supported_events(self) -> List[WorkflowEventType]:
        """
        Get the list of supported workflow event types.
        
        Returns:
            List of supported WorkflowEventType values
        """
        return list(WORKFLOW_TO_N8N_EVENT_MAP.keys())

    def _get_handler_for_event(
        self, event_type: WorkflowEventType, entity_type: str
    ) -> Optional[WebhookHandler]:
        """
        Get the appropriate handler for a given event and entity type.
        
        Args:
            event_type: The workflow event type
            entity_type: The entity type (deal, payment, etc.)
            
        Returns:
            WebhookHandler if available, None otherwise
        """
        # Map entity types to handler names
        entity_handler_map = {
            "deal": "deal",
            "payment": "payment",
            "document": "esignature",
            "agreement": "esignature",
            "approval": "approval",
        }
        
        handler_name = entity_handler_map.get(entity_type.lower())
        if handler_name:
            return self.handler_registry.get(handler_name)
        
        return None

    async def _send_generic_webhook(
        self, event_type: WebhookEvent, data: Dict[str, Any]
    ) -> WebhookResult:
        """
        Send a generic webhook when no specific handler is available.
        
        Args:
            event_type: The n8n event type
            data: The webhook data
            
        Returns:
            WebhookResult with the send result
        """
        if not self.webhook_url:
            raise WebhookError(
                "No webhook URL configured for generic webhook sending",
                error_code="no_webhook_url"
            )
        
        # Create a temporary handler for sending
        temp_handler = type(
            "TempWebhookHandler",
            (WebhookHandler,),
            {}
        )(
            webhook_url=self.webhook_url,
            api_key=self.api_key,
            signature_secret=self.signature_secret,
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_delay_seconds=self.retry_delay_seconds,
            **self.config
        )
        
        return await temp_handler.send_webhook(event_type, data)

    async def _process_generic_webhook(self, payload: Dict[str, Any]) -> WebhookResult:
        """
        Process a generic webhook when no specific handler is available.
        
        Args:
            payload: The webhook payload
            
        Returns:
            WebhookResult with the processing result
        """
        # For generic processing, we just validate and return success
        # In a real implementation, this might trigger default workflows
        event_type = payload.get("event")
        data = payload.get("data", {})
        
        return WebhookResult(
            success=True,
            event_type=WebhookEvent(event_type) if event_type else WebhookEvent.WEBHOOK_RECEIVED,
            webhook_url=self.webhook_url,
            status=WebhookStatus.COMPLETED,
            processed_at=datetime.utcnow(),
            response_data={"message": "Generic webhook processed", "data_keys": list(data.keys())},
        )