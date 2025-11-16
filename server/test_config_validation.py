"""
Test configuration validation for workflow provider settings.

This test file verifies that the configuration system properly validates
workflow provider settings and maintains backward compatibility.
"""

import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError

from app.core.config import Settings, get_settings, clear_settings_cache


class TestWorkflowProviderConfig:
    """Test workflow provider configuration validation."""

    def test_default_workflow_provider(self):
        """Test that default workflow provider is 'custom'."""
        settings = Settings()
        assert settings.workflow_provider == "custom"

    def test_valid_workflow_providers(self):
        """Test that all valid workflow providers are accepted."""
        # Test custom provider (no additional settings required)
        settings = Settings(workflow_provider="custom")
        assert settings.workflow_provider == "custom"
        
        # Test external provider (no additional settings required)
        settings = Settings(workflow_provider="external")
        assert settings.workflow_provider == "external"
        
        # Test n8n provider (requires n8n settings)
        settings = Settings(
            workflow_provider="n8n",
            n8n_webhook_url="https://test.com/webhook",
            n8n_api_key="test_api_key",
            n8n_signature_secret="test_secret"
        )
        assert settings.workflow_provider == "n8n"

    def test_invalid_workflow_provider(self):
        """Test that invalid workflow providers raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(workflow_provider="invalid")
        
        assert "workflow_provider must be one of" in str(exc_info.value)

    def test_n8n_provider_requires_all_settings(self):
        """Test that n8n provider requires all required settings."""
        # Test missing webhook URL
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                workflow_provider="n8n",
                n8n_webhook_url=None,
                n8n_api_key="test_key",
                n8n_signature_secret="test_secret"
            )
        assert "n8n_webhook_url" in str(exc_info.value)

        # Test missing API key
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                workflow_provider="n8n",
                n8n_webhook_url="https://test.com",
                n8n_api_key=None,
                n8n_signature_secret="test_secret"
            )
        assert "n8n_api_key" in str(exc_info.value)

        # Test missing signature secret
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                workflow_provider="n8n",
                n8n_webhook_url="https://test.com",
                n8n_api_key="test_key",
                n8n_signature_secret=None
            )
        assert "n8n_signature_secret" in str(exc_info.value)

        # Test empty string values
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                workflow_provider="n8n",
                n8n_webhook_url="   ",
                n8n_api_key="test_key",
                n8n_signature_secret="test_secret"
            )
        assert "n8n_webhook_url" in str(exc_info.value)

    def test_n8n_provider_with_complete_settings(self):
        """Test that n8n provider works with all required settings."""
        settings = Settings(
            workflow_provider="n8n",
            n8n_webhook_url="https://test.com/webhook",
            n8n_api_key="test_api_key",
            n8n_signature_secret="test_secret"
        )
        assert settings.workflow_provider == "n8n"
        assert settings.n8n_webhook_url == "https://test.com/webhook"
        assert settings.n8n_api_key == "test_api_key"
        assert settings.n8n_signature_secret == "test_secret"

    def test_custom_provider_optional_n8n_settings(self):
        """Test that custom provider doesn't require n8n settings."""
        settings = Settings(workflow_provider="custom")
        assert settings.workflow_provider == "custom"
        assert settings.n8n_webhook_url is None
        assert settings.n8n_api_key is None
        assert settings.n8n_signature_secret is None

    def test_external_provider_optional_n8n_settings(self):
        """Test that external provider doesn't require n8n settings."""
        settings = Settings(workflow_provider="external")
        assert settings.workflow_provider == "external"
        assert settings.n8n_webhook_url is None
        assert settings.n8n_api_key is None
        assert settings.n8n_signature_secret is None

    def test_backward_compatibility_n8n_enabled(self):
        """Test backward compatibility with n8n_enabled flag."""
        # When n8n_enabled is True and workflow_provider is default (custom),
        # it should be automatically set to 'n8n'
        settings = Settings(
            n8n_enabled=True,
            n8n_webhook_url="https://test.com/webhook",
            n8n_api_key="test_api_key",
            n8n_signature_secret="test_secret"
        )
        
        assert settings.workflow_provider == "n8n"
        assert settings.n8n_enabled is True

    def test_backward_compatibility_n8n_enabled_with_explicit_provider(self):
        """Test that explicit workflow_provider takes precedence over n8n_enabled."""
        import warnings
        
        with warnings.catch_warnings(record=True) as warning_list:
            warnings.simplefilter("always")
            
            settings = Settings(
                workflow_provider="custom",
                n8n_enabled=True,
                n8n_webhook_url="https://test.com/webhook",
                n8n_api_key="test_api_key",
                n8n_signature_secret="test_secret"
            )
        
        # Should keep the explicit workflow_provider
        assert settings.workflow_provider == "custom"
        assert settings.n8n_enabled is True
        
        # Should issue a warning about the inconsistency
        warning_messages = [str(w.message) for w in warning_list]
        assert any("n8n_enabled is True but workflow_provider is 'custom'" in msg for msg in warning_messages)

    def test_n8n_optional_settings_defaults(self):
        """Test that optional n8n settings have correct defaults."""
        settings = Settings(
            workflow_provider="n8n",
            n8n_webhook_url="https://test.com/webhook",
            n8n_api_key="test_api_key",
            n8n_signature_secret="test_secret"
        )
        
        assert settings.n8n_timeout_seconds == 30
        assert settings.n8n_retry_attempts == 3
        assert settings.n8n_retry_delay_seconds == 5

    def test_n8n_optional_settings_custom_values(self):
        """Test that optional n8n settings can be customized."""
        settings = Settings(
            workflow_provider="n8n",
            n8n_webhook_url="https://test.com/webhook",
            n8n_api_key="test_api_key",
            n8n_signature_secret="test_secret",
            n8n_timeout_seconds=60,
            n8n_retry_attempts=5,
            n8n_retry_delay_seconds=10
        )
        
        assert settings.n8n_timeout_seconds == 60
        assert settings.n8n_retry_attempts == 5
        assert settings.n8n_retry_delay_seconds == 10


class TestSettingsCaching:
    """Test settings caching functionality."""

    def test_get_settings_caching(self):
        """Test that get_settings returns the same instance."""
        clear_settings_cache()
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2

    def test_clear_settings_cache(self):
        """Test that clear_settings_cache clears the cache."""
        settings1 = get_settings()
        clear_settings_cache()
        settings2 = get_settings()
        
        assert settings1 is not settings2

    @patch.dict(os.environ, {
        "WORKFLOW_PROVIDER": "n8n",
        "N8N_WEBHOOK_URL": "https://test.com/webhook",
        "N8N_API_KEY": "test_api_key",
        "N8N_SIGNATURE_SECRET": "test_secret"
    })
    def test_environment_variables(self):
        """Test that environment variables are properly loaded."""
        clear_settings_cache()
        settings = get_settings()
        
        assert settings.workflow_provider == "n8n"
        assert settings.n8n_webhook_url == "https://test.com/webhook"
        assert settings.n8n_api_key == "test_api_key"
        assert settings.n8n_signature_secret == "test_secret"


if __name__ == "__main__":
    pytest.main([__file__])