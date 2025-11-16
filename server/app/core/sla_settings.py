"""
SLA Dashboard-specific settings and configuration.

This module extends the base application configuration with SLA dashboard
specific settings and environment variables.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class SLASettings(BaseSettings):
    """SLA Dashboard specific settings."""

    # Business Hours Configuration
    business_hours_timezone: str = Field(
        default="US/Eastern",
        description="Timezone for business hours calculations"
    )
    business_hours_start: int = Field(
        default=9,
        ge=0, le=23,
        description="Business hours start (24-hour format)"
    )
    business_hours_end: int = Field(
        default=17,
        ge=1, le=24,
        description="Business hours end (24-hour format)"
    )
    business_workdays: str = Field(
        default="0,1,2,3,4",  # Monday-Friday
        description="Comma-separated workdays (0=Monday, 6=Sunday)"
    )

    # SLA Targets (can be overridden by environment variables)
    sla_touch_rate_target: float = Field(
        default=80.0,
        ge=0, le=100,
        description="Five-minute touch rate SLA target (%)"
    )
    sla_quote_to_cash_target: float = Field(
        default=48.0,
        ge=0,
        description="Quote-to-cash time SLA target (hours)"
    )
    sla_error_rate_target: float = Field(
        default=0.5,
        ge=0, le=100,
        description="Idempotent write error rate SLA target (%)"
    )
    sla_guardrail_compliance_target: float = Field(
        default=95.0,
        ge=0, le=100,
        description="Guardrail compliance rate SLA target (%)"
    )

    # Performance Settings
    sla_calculation_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Maximum time for SLA calculations (seconds)"
    )
    sla_parallel_calculations: bool = Field(
        default=True,
        description="Enable parallel SLA calculations"
    )
    sla_cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        description="SLA metrics cache TTL (seconds)"
    )
    sla_dashboard_refresh_interval: int = Field(
        default=300,
        ge=10,
        description="Dashboard refresh interval (seconds)"
    )

    # Data Retention
    sla_data_retention_days: int = Field(
        default=365,
        ge=1,
        description="SLA data retention period (days)"
    )
   sla_historical_aggregation_enabled: bool = Field(
        default=True,
        description="Enable historical SLA data aggregation"
    )

    # Alerting Settings
    sla_alerting_enabled: bool = Field(
        default=False,
        description="Enable SLA alerting"
    )
    sla_alert_cooldown_minutes: int = Field(
        default=60,
        ge=1,
        description="Alert cooldown period (minutes)"
    )
    sla_alert_webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for SLA alerts"
    )

    # Export Settings
    sla_export_enabled: bool = Field(
        default=True,
        description="Enable SLA metrics export"
    )
    sla_export_formats: str = Field(
        default="json,csv",
        description="Allowed export formats (comma-separated)"
    )
    sla_export_max_records: int = Field(
        default=10000,
        ge=1,
        description="Maximum records per export"
    )

    # Monitoring and Health
    sla_health_check_enabled: bool = Field(
        default=True,
        description="Enable SLA service health checks"
    )
    sla_metrics_collection_enabled: bool = Field(
        default=True,
        description="Enable SLA metrics collection for monitoring"
    )

    # Database Optimization
    sla_use_db_views: bool = Field(
        default=True,
        description="Use optimized database views for SLA calculations"
    )
    sla_db_query_timeout_seconds: int = Field(
        default=25,
        ge=1,
        description="Database query timeout for SLA calculations (seconds)"
    )

    @field_validator('business_workdays')
    @classmethod
    def validate_workdays(cls, v):
        """Validate workdays format."""
        try:
            days = [int(d.strip()) for d in v.split(',')]
            if any(d < 0 or d > 6 for d in days):
                raise ValueError("Workdays must be between 0 (Monday) and 6 (Sunday)")
            return v
        except ValueError:
            raise ValueError("Workdays must be comma-separated integers (0-6)")

    @field_validator('business_hours_end')
    @classmethod
    def validate_business_hours(cls, v, info):
        """Validate business hours end is after start."""
        if 'business_hours_start' in info.data and v <= info.data['business_hours_start']:
            raise ValueError("Business hours end must be after start")
        return v

    @field_validator('sla_export_formats')
    @classmethod
    def validate_export_formats(cls, v):
        """Validate export formats."""
        allowed_formats = {"json", "csv", "xml", "xlsx"}
        formats = [f.strip().lower() for f in v.split(',')]
        if any(f not in allowed_formats for f in formats):
            raise ValueError(f"Export formats must be one of: {', '.join(allowed_formats)}")
        return v

    def get_workdays_list(self) -> List[int]:
        """Get workdays as a list of integers."""
        return [int(d.strip()) for d in self.business_workdays.split(',')]

    def get_export_formats_list(self) -> List[str]:
        """Get export formats as a list."""
        return [f.strip().lower() for f in self.sla_export_formats.split(',')]

    def get_sla_targets(self) -> dict:
        """Get all SLA targets as a dictionary."""
        return {
            "touch_rate": self.sla_touch_rate_target,
            "quote_to_cash": self.sla_quote_to_cash_target,
            "error_rate": self.sla_error_rate_target,
            "guardrail_compliance": self.sla_guardrail_compliance_target,
        }


@lru_cache(maxsize=None)
def get_sla_settings() -> SLASettings:
    """
    Get cached SLA settings instance.

    Uses lru_cache to ensure the same settings instance is returned
    throughout the application lifecycle.

    Returns:
        SLASettings: The cached SLA settings instance
    """
    return SLASettings()


def clear_sla_settings_cache() -> None:
    """
    Clear the cached SLA settings instance.

    Useful for testing or when configuration needs to be reloaded.
    """
    get_sla_settings.cache_clear()