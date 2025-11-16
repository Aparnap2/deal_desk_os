from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.services.workflow_engine import (
    WorkflowEngine,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowResult,
    WorkflowStatus,
)

logger = get_logger(__name__)


class CustomWorkflowEngine(WorkflowEngine):
    """
    Custom implementation of the WorkflowEngine interface.
    Handles basic workflow logic for deal creation, payment success, etc.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the custom workflow engine.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._supported_events = list(WorkflowEventType)
        logger.info("CustomWorkflowEngine initialized", config=self.config)

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
        start_time = time.time()
        workflow_id = str(uuid.uuid4())
        
        logger.info(
            "Triggering workflow",
            workflow_id=workflow_id,
            event_type=event.event_type.value,
            entity_id=event.entity_id,
            entity_type=event.entity_type,
        )

        try:
            if not self.is_event_supported(event.event_type):
                result = WorkflowResult(
                    workflow_id=workflow_id,
                    status=WorkflowStatus.FAILED,
                    event_type=event.event_type,
                    entity_id=event.entity_id,
                    message=f"Unsupported event type: {event.event_type.value}",
                    error_details={"event_type": event.event_type.value},
                )
                logger.warning(
                    "Unsupported event type",
                    workflow_id=workflow_id,
                    event_type=event.event_type.value,
                )
                return result

            # Process the event based on its type
            output_data = await self._process_event(event)
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            result = WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.COMPLETED,
                event_type=event.event_type,
                entity_id=event.entity_id,
                message=f"Successfully processed {event.event_type.value} event",
                output_data=output_data,
                execution_time_ms=execution_time_ms,
            )
            
            logger.info(
                "Workflow completed successfully",
                workflow_id=workflow_id,
                event_type=event.event_type.value,
                execution_time_ms=execution_time_ms,
            )
            
            return result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": logger.exception("Workflow execution failed") if logger else None,
            }
            
            result = WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.FAILED,
                event_type=event.event_type,
                entity_id=event.entity_id,
                message=f"Failed to process {event.event_type.value} event: {str(e)}",
                error_details=error_details,
                execution_time_ms=execution_time_ms,
            )
            
            logger.error(
                "Workflow execution failed",
                workflow_id=workflow_id,
                event_type=event.event_type.value,
                error=str(e),
                execution_time_ms=execution_time_ms,
            )
            
            return result

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
        start_time = time.time()
        workflow_id = str(uuid.uuid4())
        
        logger.info(
            "Processing webhook",
            workflow_id=workflow_id,
            webhook_type=webhook_type,
            payload_keys=list(payload.keys()),
        )

        try:
            # Convert webhook to workflow event
            event = await self._webhook_to_event(webhook_type, payload, headers)
            
            if not event:
                result = WorkflowResult(
                    workflow_id=workflow_id,
                    status=WorkflowStatus.FAILED,
                    event_type=WorkflowEventType.DEAL_CREATED,  # Default event type
                    entity_id=payload.get("id", "unknown"),
                    message=f"Unknown webhook type: {webhook_type}",
                    error_details={"webhook_type": webhook_type},
                )
                logger.warning(
                    "Unknown webhook type",
                    workflow_id=workflow_id,
                    webhook_type=webhook_type,
                )
                return result

            # Process the converted event
            return await self.trigger_workflow(event)

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
            }
            
            result = WorkflowResult(
                workflow_id=workflow_id,
                status=WorkflowStatus.FAILED,
                event_type=WorkflowEventType.DEAL_CREATED,  # Default event type
                entity_id=payload.get("id", "unknown"),
                message=f"Failed to process webhook {webhook_type}: {str(e)}",
                error_details=error_details,
                execution_time_ms=execution_time_ms,
            )
            
            logger.error(
                "Webhook processing failed",
                workflow_id=workflow_id,
                webhook_type=webhook_type,
                error=str(e),
            )
            
            return result

    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the workflow engine.
        
        Returns:
            Dict containing health status information
        """
        try:
            # Perform basic health checks
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "engine_type": "custom",
                "supported_events": [event.value for event in self._supported_events],
                "config": self.config,
            }
            
            logger.info("Health check completed", status=health_status["status"])
            return health_status
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "engine_type": "custom",
                "error": str(e),
            }

    def get_supported_events(self) -> List[WorkflowEventType]:
        """
        Get the list of supported workflow event types.
        
        Returns:
            List of supported WorkflowEventType values
        """
        return self._supported_events.copy()

    async def _process_event(self, event: WorkflowEvent) -> Dict[str, Any]:
        """
        Process a workflow event based on its type.
        
        Args:
            event: The workflow event to process
            
        Returns:
            Dict containing output data from the processing
        """
        if event.event_type == WorkflowEventType.DEAL_CREATED:
            return await self._handle_deal_created(event)
        elif event.event_type == WorkflowEventType.DEAL_UPDATED:
            return await self._handle_deal_updated(event)
        elif event.event_type == WorkflowEventType.DEAL_STAGE_CHANGED:
            return await self._handle_deal_stage_changed(event)
        elif event.event_type == WorkflowEventType.PAYMENT_SUCCESS:
            return await self._handle_payment_success(event)
        elif event.event_type == WorkflowEventType.PAYMENT_FAILED:
            return await self._handle_payment_failed(event)
        elif event.event_type == WorkflowEventType.DOCUMENT_SIGNED:
            return await self._handle_document_signed(event)
        elif event.event_type == WorkflowEventType.APPROVAL_GRANTED:
            return await self._handle_approval_granted(event)
        elif event.event_type == WorkflowEventType.APPROVAL_REJECTED:
            return await self._handle_approval_rejected(event)
        elif event.event_type == WorkflowEventType.GUARDRAIL_VIOLATION:
            return await self._handle_guardrail_violation(event)
        elif event.event_type == WorkflowEventType.QUOTE_GENERATED:
            return await self._handle_quote_generated(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

    async def _webhook_to_event(
        self,
        webhook_type: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[WorkflowEvent]:
        """
        Convert a webhook to a workflow event.
        
        Args:
            webhook_type: The type of webhook
            payload: The webhook payload
            headers: Optional HTTP headers
            
        Returns:
            WorkflowEvent or None if conversion fails
        """
        # Map webhook types to event types
        webhook_to_event_mapping = {
            "stripe.payment_success": WorkflowEventType.PAYMENT_SUCCESS,
            "stripe.payment_failed": WorkflowEventType.PAYMENT_FAILED,
            "docusign.signed": WorkflowEventType.DOCUMENT_SIGNED,
            "hellosign.signed": WorkflowEventType.DOCUMENT_SIGNED,
            "deal.created": WorkflowEventType.DEAL_CREATED,
            "deal.updated": WorkflowEventType.DEAL_UPDATED,
        }
        
        event_type = webhook_to_event_mapping.get(webhook_type)
        if not event_type:
            return None
        
        # Extract entity information from payload
        entity_id = payload.get("id") or payload.get("entity_id") or "unknown"
        entity_type = payload.get("entity_type") or "unknown"
        
        return WorkflowEvent(
            event_type=event_type,
            entity_id=entity_id,
            entity_type=entity_type,
            payload=payload,
            metadata={"webhook_type": webhook_type, "headers": headers},
        )

    # Event handlers
    async def _handle_deal_created(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle deal creation event."""
        logger.info("Processing deal creation", deal_id=event.entity_id)
        # Simulate processing time
        await asyncio.sleep(0.1)
        return {
            "action": "deal_created_notification_sent",
            "deal_id": event.entity_id,
            "recipients": ["sales-team@example.com"],
        }

    async def _handle_deal_updated(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle deal update event."""
        logger.info("Processing deal update", deal_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "deal_updated_notification_sent",
            "deal_id": event.entity_id,
            "updated_fields": list(event.payload.keys()),
        }

    async def _handle_deal_stage_changed(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle deal stage change event."""
        logger.info("Processing deal stage change", deal_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "stage_change_processed",
            "deal_id": event.entity_id,
            "new_stage": event.payload.get("new_stage"),
            "previous_stage": event.payload.get("previous_stage"),
        }

    async def _handle_payment_success(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle payment success event."""
        logger.info("Processing payment success", payment_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "payment_success_processed",
            "payment_id": event.entity_id,
            "amount": event.payload.get("amount"),
            "currency": event.payload.get("currency"),
        }

    async def _handle_payment_failed(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle payment failure event."""
        logger.info("Processing payment failure", payment_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "payment_failure_processed",
            "payment_id": event.entity_id,
            "error_code": event.payload.get("error_code"),
            "retry_scheduled": True,
        }

    async def _handle_document_signed(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle document signing event."""
        logger.info("Processing document signature", document_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "document_signature_processed",
            "document_id": event.entity_id,
            "signer": event.payload.get("signer_email"),
        }

    async def _handle_approval_granted(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle approval granted event."""
        logger.info("Processing approval granted", approval_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "approval_granted_processed",
            "approval_id": event.entity_id,
            "approver": event.payload.get("approver_id"),
        }

    async def _handle_approval_rejected(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle approval rejected event."""
        logger.info("Processing approval rejection", approval_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "approval_rejection_processed",
            "approval_id": event.entity_id,
            "approver": event.payload.get("approver_id"),
            "reason": event.payload.get("reason"),
        }

    async def _handle_guardrail_violation(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle guardrail violation event."""
        logger.info("Processing guardrail violation", deal_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "guardrail_violation_processed",
            "deal_id": event.entity_id,
            "violation_type": event.payload.get("violation_type"),
            "escalation_sent": True,
        }

    async def _handle_quote_generated(self, event: WorkflowEvent) -> Dict[str, Any]:
        """Handle quote generation event."""
        logger.info("Processing quote generation", deal_id=event.entity_id)
        await asyncio.sleep(0.1)
        return {
            "action": "quote_generation_processed",
            "deal_id": event.entity_id,
            "quote_number": event.payload.get("quote_number"),
            "delivery_scheduled": True,
        }