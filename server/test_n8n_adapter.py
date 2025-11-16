"""
Test script for n8n workflow adapter.

This script tests the basic functionality of the n8n adapter
to ensure it properly implements the WorkflowEngine interface.
"""

import asyncio
from datetime import datetime
from app.integrations.n8n.adapter import N8nWorkflowAdapter
from app.services.workflow_engine import WorkflowEvent, WorkflowEventType


async def test_n8n_adapter():
    """Test basic n8n adapter functionality."""
    
    # Test with n8n disabled
    print("Testing n8n adapter with n8n disabled...")
    disabled_config = {"enabled": False}
    adapter = N8nWorkflowAdapter(config=disabled_config)
    
    # Test triggering workflow when disabled
    event = WorkflowEvent(
        event_type=WorkflowEventType.DEAL_CREATED,
        entity_id="test_deal_123",
        entity_type="deal",
        payload={"amount": 1000, "currency": "USD"}
    )
    
    result = await adapter.trigger_workflow(event)
    print(f"Disabled result: {result.status} - {result.message}")
    
    # Test health check when disabled
    health = await adapter.health_check()
    print(f"Disabled health: {health['status']} - {health['message']}")
    
    # Test with n8n enabled but no webhook URL
    print("\nTesting n8n adapter with n8n enabled but no webhook URL...")
    enabled_config = {"enabled": True}
    adapter = N8nWorkflowAdapter(config=enabled_config)
    
    result = await adapter.trigger_workflow(event)
    print(f"No webhook result: {result.status} - {result.message}")
    
    # Test health check with no webhook URL
    health = await adapter.health_check()
    print(f"No webhook health: {health['status']} - {health['message']}")
    
    # Test with n8n enabled and webhook URL
    print("\nTesting n8n adapter with n8n enabled and webhook URL...")
    full_config = {
        "enabled": True,
        "webhook_url": "https://test.n8n.webhook.url",
        "api_key": "test_api_key",
        "signature_secret": "test_secret"
    }
    adapter = N8nWorkflowAdapter(config=full_config)
    
    # Test supported events
    supported_events = adapter.get_supported_events()
    print(f"Supported events: {[e.value for e in supported_events]}")
    
    # Test health check with webhook URL
    health = await adapter.health_check()
    print(f"Full config health: {health['status']} - {health['message']}")
    
    # Test webhook handling
    webhook_payload = {
        "event": "deal.created",
        "data": {
            "deal_id": "test_deal_456",
            "amount": 2000,
            "currency": "USD"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    webhook_result = await adapter.handle_webhook("deal.created", webhook_payload)
    print(f"Webhook result: {webhook_result.status} - {webhook_result.message}")
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(test_n8n_adapter())