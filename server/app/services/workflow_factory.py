from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.custom_workflow_engine import CustomWorkflowEngine
from app.services.workflow_engine import WorkflowEngine
from app.integrations.n8n.adapter import N8nWorkflowAdapter

logger = get_logger(__name__)


class WorkflowEngineFactory:
    """
    Factory class for creating workflow engine instances.
    Supports different workflow engine implementations based on configuration.
    """

    _instance: Optional[WorkflowEngineFactory] = None
    _workflow_engine: Optional[WorkflowEngine] = None

    def __new__(cls) -> WorkflowEngineFactory:
        """
        Implement singleton pattern for the factory.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the factory if not already initialized.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.settings = get_settings()
        self._initialized = True
        logger.info("WorkflowEngineFactory initialized")

    def create_workflow_engine(
        self,
        engine_type: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> WorkflowEngine:
        """
        Create a workflow engine instance based on the specified type and configuration.
        
        Args:
            engine_type: The type of workflow engine to create. If None, uses default from config.
            config: Optional configuration dictionary for the engine
            
        Returns:
            WorkflowEngine: The created workflow engine instance
            
        Raises:
            ValueError: If the specified engine type is not supported
        """
        if engine_type is None:
            engine_type = getattr(self.settings, 'workflow_provider', 'custom')
        
        if config is None:
            config = getattr(self.settings, 'workflow_engine_config', {})

        logger.info(
            "Creating workflow engine",
            engine_type=engine_type,
            config_keys=list(config.keys()),
        )

        if engine_type.lower() == 'custom':
            return self._create_custom_engine(config)
        elif engine_type.lower() == 'n8n':
            return self._create_n8n_engine(config)
        elif engine_type.lower() == 'external':
            return self._create_external_engine(config)
        else:
            raise ValueError(f"Unsupported workflow engine type: {engine_type}")

    def _create_custom_engine(self, config: Dict[str, Any]) -> CustomWorkflowEngine:
        """
        Create a custom workflow engine instance.
        
        Args:
            config: Configuration dictionary for the custom engine
            
        Returns:
            CustomWorkflowEngine: The created custom workflow engine
        """
        logger.info("Creating CustomWorkflowEngine", config=config)
        return CustomWorkflowEngine(config=config)

    def _create_n8n_engine(self, config: Dict[str, Any]) -> WorkflowEngine:
        """
        Create an n8n workflow engine instance.
        
        Args:
            config: Configuration dictionary for the n8n engine
            
        Returns:
            WorkflowEngine: The created n8n workflow engine
            
        """
        logger.info("Creating n8n workflow engine", config=config)
        
        # Merge with settings if not provided in config
        n8n_config = {
            "enabled": getattr(self.settings, 'n8n_enabled', False),
            "webhook_url": getattr(self.settings, 'n8n_webhook_url', None),
            "api_key": getattr(self.settings, 'n8n_api_key', None),
            "signature_secret": getattr(self.settings, 'n8n_signature_secret', None),
            "timeout_seconds": getattr(self.settings, 'n8n_timeout_seconds', 30),
            "retry_attempts": getattr(self.settings, 'n8n_retry_attempts', 3),
            "retry_delay_seconds": getattr(self.settings, 'n8n_retry_delay_seconds', 5),
            **config  # Override with provided config
        }
        
        return N8nWorkflowAdapter(config=n8n_config)

    def _create_external_engine(self, config: Dict[str, Any]) -> WorkflowEngine:
        """
        Create an external workflow engine instance.
        
        Args:
            config: Configuration dictionary for the external engine
            
        Returns:
            WorkflowEngine: The created external workflow engine
            
        Raises:
            NotImplementedError: External engine not yet implemented
        """
        logger.info("External workflow engine requested", config=config)
        # TODO: Implement external workflow engine
        raise NotImplementedError("External workflow engine is not yet implemented")

    def get_default_workflow_engine(self) -> WorkflowEngine:
        """
        Get the default workflow engine instance based on configuration.
        
        Returns:
            WorkflowEngine: The default workflow engine instance
        """
        if self._workflow_engine is None:
            self._workflow_engine = self.create_workflow_engine()
        return self._workflow_engine

    def reset_workflow_engine(self) -> None:
        """
        Reset the cached workflow engine instance.
        Useful for testing or configuration changes.
        """
        self._workflow_engine = None
        logger.info("Workflow engine cache reset")


# Global factory instance
_factory: Optional[WorkflowEngineFactory] = None


def get_workflow_engine_factory() -> WorkflowEngineFactory:
    """
    Get the singleton workflow engine factory instance.
    
    Returns:
        WorkflowEngineFactory: The factory instance
    """
    global _factory
    if _factory is None:
        _factory = WorkflowEngineFactory()
    return _factory


def get_workflow_engine(
    engine_type: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> WorkflowEngine:
    """
    Get a workflow engine instance.
    This is the main entry point for getting workflow engines in the application.
    
    Args:
        engine_type: Optional engine type. If None, uses default from configuration.
        config: Optional configuration dictionary
        
    Returns:
        WorkflowEngine: The workflow engine instance
    """
    factory = get_workflow_engine_factory()
    
    if engine_type is None and config is None:
        # Return the default singleton instance
        return factory.get_default_workflow_engine()
    else:
        # Create a new instance with the specified parameters
        return factory.create_workflow_engine(engine_type=engine_type, config=config)


def reset_workflow_engine_cache() -> None:
    """
    Reset the workflow engine cache.
    Useful for testing or when configuration changes.
    """
    global _factory
    if _factory is not None:
        _factory.reset_workflow_engine()
    _factory = None
    logger.info("Workflow engine factory cache reset")