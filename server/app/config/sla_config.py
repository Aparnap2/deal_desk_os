"""
SLA Dashboard configuration and alerting thresholds.

This module defines the configuration for SLA monitoring including
target thresholds, alerting rules, and business hours settings.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels for SLA violations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DayOfWeek(str, Enum):
    """Days of the week for business hours configuration."""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


@dataclass
class SLATarget:
    """Individual SLA target configuration."""
    name: str
    target_value: float
    unit: str
    description: str
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None


@dataclass
class BusinessHoursConfig:
    """Business hours configuration for SLA calculations."""
    timezone: str = "US/Eastern"
    start_hour: int = 9
    end_hour: int = 17
    workdays: List[DayOfWeek] = None

    def __post_init__(self):
        if self.workdays is None:
            self.workdays = [
                DayOfWeek.MONDAY,
                DayOfWeek.TUESDAY,
                DayOfWeek.WEDNESDAY,
                DayOfWeek.THURSDAY,
                DayOfWeek.FRIDAY
            ]


@dataclass
class AlertRule:
    """Alert rule configuration for SLA monitoring."""
    metric_name: str
    condition: str  # "gt", "lt", "eq", "gte", "lte"
    threshold: float
    severity: AlertSeverity
    message_template: str
    cooldown_minutes: int = 60  # Minimum time between same alerts


@dataclass
class SLAConfig:
    """Complete SLA configuration."""
    # SLA Targets
    five_minute_touch_rate: SLATarget = SLATarget(
        name="Five Minute Touch Rate",
        target_value=80.0,
        unit="percentage",
        description="Percentage of deals touched within 5 minutes during business hours",
        warning_threshold=75.0,
        critical_threshold=70.0
    )

    quote_to_cash_time: SLATarget = SLATarget(
        name="Quote to Cash Time",
        target_value=48.0,
        unit="hours",
        description="Median time from quote generation to payment collection",
        warning_threshold=60.0,
        critical_threshold=72.0
    )

    idempotent_write_error_rate: SLATarget = SLATarget(
        name="Idempotent Write Error Rate",
        target_value=0.5,
        unit="percentage",
        description="Percentage of failed idempotent write operations",
        warning_threshold=0.75,
        critical_threshold=1.0
    )

    guardrail_compliance_rate: SLATarget = SLATarget(
        name="Guardrail Compliance Rate",
        target_value=95.0,
        unit="percentage",
        description="Percentage of deals passing guardrail validation",
        warning_threshold=90.0,
        critical_threshold=85.0
    )

    # Business hours configuration
    business_hours: BusinessHoursConfig = BusinessHoursConfig()

    # Alerting rules
    alert_rules: List[AlertRule] = None

    # Dashboard refresh intervals (in seconds)
    dashboard_refresh_interval: int = 300  # 5 minutes
    metrics_cache_ttl: int = 60  # 1 minute

    # Data retention settings
    data_retention_days: int = 365
    historical_aggregation_enabled: bool = True

    # Performance settings
    max_calculation_time_seconds: int = 30
    enable_parallel_calculations: bool = True

    def __post_init__(self):
        if self.alert_rules is None:
            self.alert_rules = self._create_default_alert_rules()

    def _create_default_alert_rules(self) -> List[AlertRule]:
        """Create default alerting rules."""
        return [
            AlertRule(
                metric_name="touch_rate_percentage",
                condition="lt",
                threshold=self.five_minute_touch_rate.warning_threshold,
                severity=AlertSeverity.MEDIUM,
                message_template="Touch rate has fallen to {value:.2f}% (target: {target}%)"
            ),
            AlertRule(
                metric_name="touch_rate_percentage",
                condition="lt",
                threshold=self.five_minute_touch_rate.critical_threshold,
                severity=AlertSeverity.CRITICAL,
                message_template="CRITICAL: Touch rate has fallen to {value:.2f}% (target: {target}%)"
            ),
            AlertRule(
                metric_name="median_quote_to_cash_hours",
                condition="gt",
                threshold=self.quote_to_cash_time.warning_threshold,
                severity=AlertSeverity.MEDIUM,
                message_template="Quote-to-cash time has increased to {value:.2f} hours (target: {target} hours)"
            ),
            AlertRule(
                metric_name="median_quote_to_cash_hours",
                condition="gt",
                threshold=self.quote_to_cash_time.critical_threshold,
                severity=AlertSeverity.CRITICAL,
                message_template="CRITICAL: Quote-to-cash time has increased to {value:.2f} hours (target: {target} hours)"
            ),
            AlertRule(
                metric_name="failed_percentage",
                condition="gt",
                threshold=self.idempotent_write_error_rate.warning_threshold,
                severity=AlertSeverity.HIGH,
                message_template="Payment error rate has increased to {value:.3f}% (target: < {target}%)"
            ),
            AlertRule(
                metric_name="compliance_rate_percentage",
                condition="lt",
                threshold=self.guardrail_compliance_rate.warning_threshold,
                severity=AlertSeverity.MEDIUM,
                message_template="Guardrail compliance rate has fallen to {value:.2f}% (target: {target}%)"
            ),
            AlertRule(
                metric_name="compliance_rate_percentage",
                condition="lt",
                threshold=self.guardrail_compliance_rate.critical_threshold,
                severity=AlertSeverity.HIGH,
                message_template="HIGH: Guardrail compliance rate has fallen to {value:.2f}% (target: {target}%)"
            ),
        ]

    def get_sla_targets(self) -> Dict[str, SLATarget]:
        """Get all SLA targets as a dictionary."""
        return {
            "five_minute_touch_rate": self.five_minute_touch_rate,
            "quote_to_cash_time": self.quote_to_cash_time,
            "idempotent_write_error_rate": self.idempotent_write_error_rate,
            "guardrail_compliance_rate": self.guardrail_compliance_rate,
        }

    def get_alert_rules_for_metric(self, metric_name: str) -> List[AlertRule]:
        """Get alert rules for a specific metric."""
        return [rule for rule in self.alert_rules if rule.metric_name == metric_name]

    def check_sla_compliance(self, metric_name: str, actual_value: float) -> Dict[str, any]:
        """Check if a metric meets its SLA target."""
        targets = self.get_sla_targets()

        if metric_name not in targets:
            return {"compliant": None, "status": "unknown", "target": None}

        target = targets[metric_name]

        # Determine compliance based on metric type
        if metric_name in ["five_minute_touch_rate", "guardrail_compliance_rate"]:
            # Higher is better
            compliant = actual_value >= target.target_value
            if actual_value >= target.critical_threshold:
                status = "critical"
            elif actual_value >= target.warning_threshold:
                status = "warning"
            else:
                status = "compliant"
        else:
            # Lower is better (time-based and error rate metrics)
            compliant = actual_value <= target.target_value
            if actual_value <= target.critical_threshold:
                status = "critical"
            elif actual_value <= target.warning_threshold:
                status = "warning"
            else:
                status = "compliant"

        return {
            "compliant": compliant,
            "status": status,
            "target": target.target_value,
            "actual": actual_value,
            "unit": target.unit
        }


# Global SLA configuration instance
sla_config = SLAConfig()