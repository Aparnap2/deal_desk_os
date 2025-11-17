import os
from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Deal Desk OS")
    environment: str = Field(default="development")
    secret_key: str = Field(default="change-me-in-production", min_length=12)
    access_token_expire_minutes: int = Field(default=60)
    database_url: str = Field(
        default="postgresql+asyncpg://deal_desk:deal_desk@localhost:5432/deal_desk_os",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    allowed_origins: List[AnyHttpUrl] = Field(default_factory=list)
    
    # Workflow provider configuration (CODE-FIRST by default)
    workflow_provider: str = Field(default="custom", description="Workflow provider: 'custom', 'n8n', or 'external'. Default: 'custom' for code-first approach")

    # Optional n8n integration (only used when workflow_provider='n8n' or USE_N8N=true)
    use_n8n: bool = Field(default=False, description="Enable n8n workflow integration (optional)")
    n8n_enabled: bool = Field(default=False, description="Legacy flag for n8n enablement (deprecated - use use_n8n)")
    n8n_webhook_url: Optional[str] = Field(default=None, description="n8n webhook URL")
    n8n_api_key: Optional[str] = Field(default=None, description="n8n API key")
    n8n_signature_secret: Optional[str] = Field(default=None, description="n8n signature secret")
    n8n_timeout_seconds: int = Field(default=30, description="n8n request timeout in seconds")
    n8n_retry_attempts: int = Field(default=3, description="n8n retry attempts")
    n8n_retry_delay_seconds: int = Field(default=5, description="n8n retry delay in seconds")

    @model_validator(mode="before")
    @classmethod
    def validate_workflow_configuration(cls, data: dict) -> dict:
        """
        Validate workflow provider configuration and ensure consistency.
        
        This validator ensures:
        1. workflow_provider is one of allowed values
        2. When workflow_provider='n8n', all required n8n settings are present
        3. When workflow_provider='custom', n8n settings are optional
        4. Backward compatibility: if n8n_enabled=True and workflow_provider is default, set to 'n8n'
        """
        # Make a copy to avoid modifying the original
        data = data.copy()
        
        # Validate workflow_provider value if present
        workflow_provider = data.get("workflow_provider", "custom")
        allowed_providers = {"custom", "n8n", "external"}
        if workflow_provider not in allowed_providers:
            raise ValueError(
                f"workflow_provider must be one of {allowed_providers}, got '{workflow_provider}'"
            )
        
        # Support USE_N8N=true and use_n8n=true for easy n8n activation
        use_n8n = data.get("use_n8n", False) or data.get("n8n_enabled", False) or os.getenv("USE_N8N", "").lower() in ("true", "1", "yes")

        # Auto-switch to n8n if USE_N8N=true and workflow_provider is still default
        if (use_n8n and
            workflow_provider == "custom" and
            "workflow_provider" not in data):
            data["workflow_provider"] = "n8n"
            workflow_provider = "n8n"
        
        # When workflow_provider is 'n8n' AND it's actually being used, ensure required settings are present
        if workflow_provider == "n8n" and use_n8n:
            required_settings = ["n8n_webhook_url", "n8n_api_key", "n8n_signature_secret"]
            missing_settings = []

            for setting_name in required_settings:
                setting_value = data.get(setting_name)
                if not setting_value or (isinstance(setting_value, str) and setting_value.strip() == ""):
                    missing_settings.append(setting_name)

            if missing_settings:
                raise ValueError(
                    f"When workflow_provider='n8n' and use_n8n=true, the following settings are required: {', '.join(missing_settings)}"
                )

        # If n8n is configured but not being used, warn and force back to custom
        if workflow_provider == "n8n" and not use_n8n:
            logger.warning(
                f"workflow_provider='n8n' specified but use_n8n=false. Defaulting to 'custom' (code-first approach)"
            )
            data["workflow_provider"] = "custom"
        
        return data

    @model_validator(mode="after")
    def check_configuration_consistency(self) -> "Settings":
        """
        Check for configuration inconsistencies and issue warnings.
        """
        # When workflow_provider is 'custom' or 'external', n8n settings are optional
        # but if n8n_enabled is True, ensure consistency
        if self.workflow_provider in {"custom", "external"} and self.n8n_enabled:
            # Log a warning but don't raise an error for backward compatibility
            import warnings
            warnings.warn(
                f"n8n_enabled is True but workflow_provider is '{self.workflow_provider}'. "
                f"Consider setting workflow_provider to 'n8n' or n8n_enabled to False.",
                UserWarning
            )
        
        return self


@lru_cache(maxsize=None)
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache with unlimited size to ensure the same settings instance
    is returned throughout the application lifecycle. This ensures configuration
    consistency and improves performance by avoiding repeated parsing of environment
    variables and validation.
    
    Returns:
        Settings: The cached settings instance
    """
    return Settings()


def clear_settings_cache() -> None:
    """
    Clear the cached settings instance.
    
    Useful for testing or when configuration needs to be reloaded.
    After calling this function, the next call to get_settings() will
    create a new Settings instance with updated configuration.
    """
    get_settings.cache_clear()
