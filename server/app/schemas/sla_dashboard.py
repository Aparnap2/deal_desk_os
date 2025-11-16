"""
Pydantic schemas for SLA Dashboard API responses.

This module defines the data models for SLA metrics, KPIs, and dashboard
responses to ensure type safety and API contract consistency.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# Base metric response schemas
class BaseMetricResponse(BaseModel):
    """Base schema for all metric responses."""
    status: str = Field(description="Calculation status: 'success' or 'failed'")
    error: Optional[str] = Field(default=None, description="Error message if calculation failed")


class CalculationPeriod(BaseModel):
    """Date range information for metric calculations."""
    start_date: Optional[str] = Field(default=None, description="Start date in ISO format")
    end_date: Optional[str] = Field(default=None, description="End date in ISO format")


# Touch Rate Schemas
class TouchRateMetrics(BaseMetricResponse):
    """Five-minute touch rate metrics."""
    touch_rate_percentage: float = Field(description="Percentage of deals touched within 5 minutes during business hours")
    total_deals: int = Field(description="Total number of deals analyzed")
    business_hour_deals: int = Field(description="Number of deals created during business hours")
    touched_within_5min: int = Field(description="Number of deals touched within 5 minutes")
    calculation_period: CalculationPeriod = Field(description="Date range for calculation")


# Quote-to-Cash Schemas
class QuoteToCashPercentiles(BaseModel):
    """Percentile breakdown for quote-to-cash time."""
    median: float = Field(description="50th percentile (median)")
    p50: float = Field(description="50th percentile")
    p75: float = Field(description="75th percentile")
    p90: float = Field(description="90th percentile")
    p95: float = Field(description="95th percentile")


class StageBreakdown(BaseModel):
    """Breakdown of quote-to-cash stages."""
    quote_to_signed_hours: QuoteToCashPercentiles
    signed_to_payment_hours: QuoteToCashPercentiles


class TargetCompliance(BaseModel):
    """Target compliance metrics."""
    within_24h_count: int = Field(description="Number of deals completed within 24 hours")
    within_24h_percentage: float = Field(description="Percentage of deals completed within 24 hours")
    within_48h_count: int = Field(description="Number of deals completed within 48 hours")
    within_48h_percentage: float = Field(description="Percentage of deals completed within 48 hours")


class QuoteToCashMetrics(BaseMetricResponse):
    """Quote-to-cash time metrics."""
    total_deals: int = Field(description="Total number of completed deals")
    quote_to_cash_hours: QuoteToCashPercentiles = Field(description="Overall quote-to-cash time percentiles")
    stage_breakdown: StageBreakdown = Field(description="Stage-by-stage time breakdown")
    target_compliance: TargetCompliance = Field(description="Target compliance metrics")


# Error Rate Schemas
class ErrorRates(BaseModel):
    """Error rate breakdown."""
    failed_percentage: float = Field(description="Percentage of failed payment attempts")
    rolled_back_percentage: float = Field(description="Percentage of rolled back payments")
    auto_recovery_rate: float = Field(description="Percentage of failed payments that were auto-recovered")


class IdempotentWriteErrorMetrics(BaseMetricResponse):
    """Idempotent write error rate metrics."""
    total_attempts: int = Field(description="Total number of payment attempts")
    unique_transactions: int = Field(description="Number of unique transactions")
    failed_attempts: int = Field(description="Number of failed attempts")
    rolled_back_attempts: int = Field(description="Number of rolled back attempts")
    auto_recovered: int = Field(description="Number of auto-recovered payments")
    error_rates: ErrorRates = Field(description="Error rate breakdown")
    error_breakdown: Dict[str, int] = Field(description="Error code frequency breakdown")
    sla_target_met: bool = Field(description="Whether SLA target (< 0.5%) is met")


# Guardrail Compliance Schemas
class ViolationAnalysis(BaseModel):
    """Guardrail violation analysis."""
    violation_reasons: Dict[str, int] = Field(description="Count of violations by reason")
    most_common_violation: Optional[str] = Field(default=None, description="Most common violation reason")


class GuardrailComplianceMetrics(BaseMetricResponse):
    """Guardrail compliance rate metrics."""
    total_deals: int = Field(description="Total number of deals analyzed")
    passed_deals: int = Field(description="Number of deals that passed guardrails")
    violated_deals: int = Field(description="Number of deals that violated guardrails")
    locked_deals: int = Field(description="Number of deals with locked guardrails")
    compliance_rate_percentage: float = Field(description="Percentage of deals that passed guardrails")
    violation_analysis: ViolationAnalysis = Field(description="Analysis of guardrail violations")
    lock_rate_percentage: float = Field(description="Percentage of deals with locked guardrails")


# Financial Impact Schemas
class RevenueMetrics(BaseModel):
    """Revenue-related metrics."""
    total_revenue: float = Field(description="Total revenue from analyzed deals")
    orchestrated_revenue: float = Field(description="Revenue from orchestrated deals")
    manual_revenue: float = Field(description="Revenue from manual deals")
    orchestrated_percentage: float = Field(description="Percentage of revenue from orchestrated deals")


class CostMetrics(BaseModel):
    """Cost-related metrics."""
    total_operational_cost: float = Field(description="Total operational cost")
    total_manual_cost_baseline: float = Field(description="What the cost would have been with manual processing")
    cost_savings: float = Field(description="Cost savings from orchestration")
    cost_savings_percentage: float = Field(description="Percentage cost savings")


class AccelerationMetrics(BaseModel):
    """Revenue acceleration metrics."""
    accelerated_revenue: float = Field(description="Value of accelerated revenue")
    total_deals_analyzed: int = Field(description="Number of deals analyzed for acceleration")


class FinancialImpactMetrics(BaseMetricResponse):
    """Financial impact metrics."""
    total_deals: int = Field(description="Total number of deals analyzed")
    revenue_metrics: RevenueMetrics = Field(description="Revenue-related metrics")
    cost_metrics: CostMetrics = Field(description="Cost-related metrics")
    acceleration_metrics: AccelerationMetrics = Field(description="Revenue acceleration metrics")
    net_financial_impact: float = Field(description="Net financial impact (savings + acceleration)")


# SLA Status Schemas
class IndividualTargets(BaseModel):
    """Individual SLA target compliance."""
    touch_rate_met: bool
    quote_to_cash_met: bool
    error_rate_met: bool
    guardrail_compliance_met: bool


class OverallSLAStatus(BaseModel):
    """Overall SLA status summary."""
    status: str = Field(description="Overall SLA status: all_met, mostly_met, partially_met, not_met")
    overall_compliance_percentage: float = Field(description="Percentage of SLA targets met")
    targets_met: int = Field(description="Number of targets met")
    total_targets: int = Field(description="Total number of targets")
    individual_targets: IndividualTargets = Field(description="Individual target compliance")
    sla_targets: Dict[str, float] = Field(description="SLA target values")


# Dashboard Summary Schema
class SLADashboardSummary(BaseModel):
    """Complete SLA dashboard summary."""
    five_minute_touch_rate: TouchRateMetrics = Field(description="Five-minute touch rate metrics")
    quote_to_cash_time: QuoteToCashMetrics = Field(description="Quote-to-cash time metrics")
    idempotent_write_error_rate: IdempotentWriteErrorMetrics = Field(description="Error rate metrics")
    guardrail_compliance_rate: GuardrailComplianceMetrics = Field(description="Guardrail compliance metrics")
    financial_impact: FinancialImpactMetrics = Field(description="Financial impact metrics")
    overall_sla_status: OverallSLAStatus = Field(description="Overall SLA status summary")
    generated_at: str = Field(description="Timestamp when dashboard was generated")


# Export Schemas
class ExportData(BaseModel):
    """Export format data."""
    export_format: str = Field(description="Export format: json or csv")
    export_timestamp: str = Field(description="Export timestamp")
    data: Dict[str, Any] = Field(description="Exported data")


# Service Health Schema
class ServiceHealth(BaseModel):
    """Service health status."""
    status: str = Field(description="Overall service status: healthy, degraded, unhealthy")
    timestamp: str = Field(description="Health check timestamp")
    services: Dict[str, str] = Field(description="Individual service health status")
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")


# Request schemas
class SLAMetricsRequest(BaseModel):
    """Base request schema for SLA metrics."""
    start_date: Optional[date] = Field(default=None, description="Start date for filtering")
    end_date: Optional[date] = Field(default=None, description="End date for filtering")

    @field_validator('end_date')
    def validate_date_range(cls, v, values):
        """Validate that end_date is after start_date."""
        if v and 'start_date' in values and values['start_date']:
            if v < values['start_date']:
                raise ValueError('end_date must be after start_date')
        return v


class QuoteToCashRequest(SLAMetricsRequest):
    """Request schema for quote-to-cash metrics."""
    assisted_only: bool = Field(default=True, description="Include only assisted (orchestrated) deals")


class ExportRequest(SLAMetricsRequest):
    """Request schema for exporting metrics."""
    format: str = Field(default="json", pattern="^(json|csv)$", description="Export format")


# Response wrapper schemas
class SLADashboardResponse(BaseModel):
    """SLA dashboard API response wrapper."""
    success: bool = Field(description="Whether the request was successful")
    message: Optional[str] = Field(default=None, description="Response message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Response data")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Response timestamp")


# Alert schemas (for future implementation)
class SLAAlert(BaseModel):
    """SLA violation alert."""
    metric_name: str = Field(description="Name of the metric that triggered the alert")
    severity: str = Field(description="Alert severity: low, medium, high, critical")
    current_value: float = Field(description="Current metric value")
    target_value: float = Field(description="Target SLA value")
    message: str = Field(description="Alert message")
    triggered_at: str = Field(description="When the alert was triggered")
    resolved_at: Optional[str] = Field(default=None, description="When the alert was resolved")


class AlertConfig(BaseModel):
    """Alert configuration."""
    metric_name: str = Field(description="Metric to monitor")
    threshold: float = Field(description="Alert threshold")
    severity: str = Field(description="Alert severity")
    enabled: bool = Field(default=True, description="Whether alert is enabled")
    cooldown_minutes: int = Field(default=60, description="Minimum time between alerts")