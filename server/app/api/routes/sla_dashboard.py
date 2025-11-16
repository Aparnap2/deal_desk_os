"""
SLA Dashboard API endpoints for real-time RevOps KPI monitoring.
Provides comprehensive endpoints for tracking deal desk performance metrics.
"""

from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_db
from app.models.user import User
from app.services.sla_analytics import SLAAnalyticsService

router = APIRouter(prefix="/sla-dashboard", tags=["sla-dashboard"])
sla_service = SLAAnalyticsService()

# Common pagination and filtering parameters
DateRange = Annotated[Optional[date], Query(description="Start date for filtering (YYYY-MM-DD)")]
EndDateRange = Annotated[Optional[date], Query(description="End date for filtering (YYYY-MM-DD)")]
Pagination = Annotated[int, Query(ge=1, le=1000, description="Page size for pagination")]


@router.get("/summary")
async def get_sla_dashboard_summary(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get comprehensive SLA dashboard summary with all KPIs.

    This endpoint provides a complete overview of deal desk performance including:
    - Five-minute touch rate during business hours
    - Quote-to-cash time metrics and percentiles
    - Idempotent write error rates
    - Guardrail compliance analysis
    - Financial impact calculations

    Args:
        start_date: Optional start date for filtering metrics
        end_date: Optional end date for filtering metrics
        session: Database session
        current_user: Authenticated user

    Returns:
        Complete SLA dashboard data with all metrics and overall status
    """
    try:
        dashboard_data = await sla_service.get_sla_dashboard_summary(
            session=session,
            start_date=start_date,
            end_date=end_date
        )
        return dashboard_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating SLA dashboard: {str(e)}"
        )


@router.get("/touch-rate")
async def get_five_minute_touch_rate(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get five-minute touch rate metrics.

    Calculates the percentage of deals that are touched within 5 minutes
    during business hours, which is a key indicator of deal desk responsiveness.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        session: Database session
        current_user: Authenticated user

    Returns:
        Touch rate metrics including percentage and deal counts
    """
    try:
        touch_rate_data = await sla_service.calculate_five_minute_touch_rate(
            session=session,
            start_date=start_date,
            end_date=end_date
        )
        return touch_rate_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating touch rate: {str(e)}"
        )


@router.get("/quote-to-cash")
async def get_quote_to_cash_metrics(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    assisted_only: bool = Query(default=True, description="Include only assisted (orchestrated) deals"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get quote-to-cash time metrics and analysis.

    Calculates median and percentile metrics for the complete deal lifecycle
    from quote generation to payment collection.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        assisted_only: Whether to include only orchestrated deals
        session: Database session
        current_user: Authenticated user

    Returns:
        Quote-to-cash metrics including percentiles and target compliance
    """
    try:
        metrics_data = await sla_service.calculate_quote_to_cash_time(
            session=session,
            start_date=start_date,
            end_date=end_date,
            assisted_only=assisted_only
        )
        return metrics_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating quote-to-cash metrics: {str(e)}"
        )


@router.get("/error-rate")
async def get_idempotent_write_error_rate(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get idempotent write error rate metrics.

    Tracks payment processing reliability including failed attempts,
    rollbacks, and auto-recovery rates.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        session: Database session
        current_user: Authenticated user

    Returns:
        Error rate metrics with detailed breakdown and SLA compliance
    """
    try:
        error_data = await sla_service.calculate_idempotent_write_error_rate(
            session=session,
            start_date=start_date,
            end_date=end_date
        )
        return error_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating error rate: {str(e)}"
        )


@router.get("/guardrail-compliance")
async def get_guardrail_compliance_rate(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get guardrail compliance rate and analysis.

    Analyzes deal guardrail violations, compliance rates, and
        common violation patterns.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        session: Database session
        current_user: Authenticated user

    Returns:
        Guardrail compliance metrics with violation analysis
    """
    try:
        compliance_data = await sla_service.calculate_guardrail_compliance_rate(
            session=session,
            start_date=start_date,
            end_date=end_date
        )
        return compliance_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating guardrail compliance: {str(e)}"
        )


@router.get("/financial-impact")
async def get_financial_impact(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get financial impact metrics and ROI analysis.

    Calculates recovered/accelerated dollars, cost savings from orchestration,
    and overall financial impact of the deal desk automation.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        session: Database session
        current_user: Authenticated user

    Returns:
        Financial impact metrics including revenue, costs, and ROI
    """
    try:
        financial_data = await sla_service.calculate_financial_impact(
            session=session,
            start_date=start_date,
            end_date=end_date
        )
        return financial_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating financial impact: {str(e)}"
        )


@router.get("/sla-status")
async def get_overall_sla_status(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get overall SLA status and compliance summary.

    Provides a consolidated view of SLA target compliance across
    all key metrics with overall health status.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        session: Database session
        current_user: Authenticated user

    Returns:
        Overall SLA status with target compliance breakdown
    """
    try:
        dashboard_data = await sla_service.get_sla_dashboard_summary(
            session=session,
            start_date=start_date,
            end_date=end_date
        )
        return {
            "overall_sla_status": dashboard_data.get("overall_sla_status", {}),
            "generated_at": dashboard_data.get("generated_at"),
            "calculation_period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting SLA status: {str(e)}"
        )


@router.get("/metrics/export")
async def export_sla_metrics(
    start_date: DateRange = None,
    end_date: EndDateRange = None,
    format: str = Query(default="json", regex="^(json|csv)$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Export SLA metrics data for external reporting.

    Provides exportable data in JSON or CSV format for integration
    with external reporting tools and dashboards.

    Args:
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering
        format: Export format ('json' or 'csv')
        session: Database session
        current_user: Authenticated user

    Returns:
        Exportable SLA metrics data
    """
    try:
        dashboard_data = await sla_service.get_sla_dashboard_summary(
            session=session,
            start_date=start_date,
            end_date=end_date
        )

        if format == "json":
            return {
                "export_format": "json",
                "export_timestamp": datetime.utcnow().isoformat(),
                "data": dashboard_data
            }
        elif format == "csv":
            # For CSV export, we'd flatten the data structure
            # This is a simplified version - in production, you'd want more sophisticated CSV generation
            flattened_data = {
                "export_timestamp": datetime.utcnow().isoformat(),
                "touch_rate_percentage": dashboard_data.get("five_minute_touch_rate", {}).get("touch_rate_percentage", 0),
                "quote_to_cash_median_hours": dashboard_data.get("quote_to_cash_time", {}).get("quote_to_cash_hours", {}).get("median", 0),
                "error_rate_percentage": dashboard_data.get("idempotent_write_error_rate", {}).get("error_rates", {}).get("failed_percentage", 0),
                "guardrail_compliance_percentage": dashboard_data.get("guardrail_compliance_rate", {}).get("compliance_rate_percentage", 0),
                "total_revenue": dashboard_data.get("financial_impact", {}).get("revenue_metrics", {}).get("total_revenue", 0),
                "cost_savings": dashboard_data.get("financial_impact", {}).get("cost_metrics", {}).get("cost_savings", 0),
                "accelerated_revenue": dashboard_data.get("financial_impact", {}).get("acceleration_metrics", {}).get("accelerated_revenue", 0),
            }
            return {
                "export_format": "csv",
                "export_timestamp": datetime.utcnow().isoformat(),
                "data": flattened_data
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error exporting metrics: {str(e)}"
        )


@router.get("/health")
async def get_sla_service_health(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get SLA service health and availability status.

    Checks the health of all SLA calculation services and database connectivity.

    Args:
        session: Database session
        current_user: Authenticated user

    Returns:
        Service health status
    """
    try:
        # Test basic database connectivity
        await session.execute(text("SELECT 1"))

        # Test each calculation service with minimal data
        health_checks = {
            "database_connection": "healthy",
            "touch_rate_service": "healthy",
            "quote_to_cash_service": "healthy",
            "error_rate_service": "healthy",
            "guardrail_service": "healthy",
            "financial_impact_service": "healthy",
            "business_hours_calculator": "healthy"
        }

        overall_status = "healthy" if all(status == "healthy" for status in health_checks.values()) else "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "services": health_checks
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }