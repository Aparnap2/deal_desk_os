"""Add SLA analytics database views

Revision ID: 20251116_001
Revises:
Create Date: 2025-11-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251116_001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create optimized database views for SLA analytics."""

    # Create view for deal lifecycle timing analysis
    op.execute("""
    CREATE OR REPLACE VIEW v_deal_lifecycle_metrics AS
    SELECT
        d.id,
        d.name,
        d.amount,
        d.currency,
        d.stage,
        d.orchestration_mode,
        d.guardrail_status,
        d.created_at,
        d.quote_generated_at,
        d.agreement_signed_at,
        d.payment_collected_at,
        d.operational_cost,
        d.manual_cost_baseline,
        -- Calculate time differences in hours
        CASE
            WHEN d.quote_generated_at IS NOT NULL AND d.created_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (d.quote_generated_at - d.created_at)) / 3600
            ELSE NULL
        END as creation_to_quote_hours,
        CASE
            WHEN d.agreement_signed_at IS NOT NULL AND d.quote_generated_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (d.agreement_signed_at - d.quote_generated_at)) / 3600
            ELSE NULL
        END as quote_to_signed_hours,
        CASE
            WHEN d.payment_collected_at IS NOT NULL AND d.agreement_signed_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (d.payment_collected_at - d.agreement_signed_at)) / 3600
            ELSE NULL
        END as signed_to_payment_hours,
        CASE
            WHEN d.payment_collected_at IS NOT NULL AND d.quote_generated_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (d.payment_collected_at - d.quote_generated_at)) / 3600
            ELSE NULL
        END as quote_to_cash_hours,
        -- Check if processed within business hours target (5 minutes)
        CASE
            WHEN d.quote_generated_at IS NOT NULL
                 AND d.created_at IS NOT NULL
                 AND EXTRACT(EPOCH FROM (d.quote_generated_at - d.created_at)) / 60 <= 5
            THEN true
            ELSE false
        END as touched_within_5min,
        -- Check if quote generated during business hours (9-5 Mon-Fri)
        CASE
            WHEN d.quote_generated_at IS NOT NULL
                 AND EXTRACT(ISODOW FROM d.quote_generated_at) <= 5
                 AND EXTRACT(HOUR FROM d.quote_generated_at) BETWEEN 9 AND 16
            THEN true
            ELSE false
        END as quote_during_business_hours
    FROM deals d
    WHERE d.quote_generated_at IS NOT NULL;
    """)

    # Create view for payment error rate analysis
    op.execute("""
    CREATE OR REPLACE VIEW v_payment_error_metrics AS
    SELECT
        p.id,
        p.deal_id,
        p.status,
        p.amount,
        p.idempotency_key,
        p.attempt_number,
        p.failure_reason,
        p.error_code,
        p.auto_recovered,
        p.created_at,
        d.amount as deal_amount,
        -- Check if payment attempt failed
        CASE
            WHEN p.status = 'failed' THEN 1
            ELSE 0
        END as is_failed,
        -- Check if payment was rolled back
        CASE
            WHEN p.status = 'rolled_back' THEN 1
            ELSE 0
        END as is_rolled_back,
        -- Check if auto-recovered
        CASE
            WHEN p.auto_recovered = true THEN 1
            ELSE 0
        END as is_auto_recovered
    FROM payments p
    LEFT JOIN deals d ON p.deal_id = d.id;
    """)

    # Create view for guardrail compliance analysis
    op.execute("""
    CREATE OR REPLACE VIEW v_guardrail_compliance_metrics AS
    SELECT
        d.id,
        d.name,
        d.amount,
        d.stage,
        d.guardrail_status,
        d.guardrail_reason,
        d.guardrail_locked,
        d.created_at,
        d.orchestration_mode,
        -- Check if guardrail passed
        CASE
            WHEN d.guardrail_status = 'pass' THEN 1
            ELSE 0
        END as guardrail_passed,
        -- Check if guardrail violated
        CASE
            WHEN d.guardrail_status = 'violated' THEN 1
            ELSE 0
        END as guardrail_violated,
        -- Check if guardrail is locked
        CASE
            WHEN d.guardrail_locked = true THEN 1
            ELSE 0
        END as guardrail_locked_count
    FROM deals d;
    """)

    # Create view for financial impact analysis
    op.execute("""
    CREATE OR REPLACE VIEW v_financial_impact_metrics AS
    SELECT
        d.id,
        d.name,
        d.amount,
        d.operational_cost,
        d.manual_cost_baseline,
        d.orchestration_mode,
        d.stage,
        d.created_at,
        d.quote_generated_at,
        d.payment_collected_at,
        -- Calculate cost savings
        (d.manual_cost_baseline - d.operational_cost) as cost_savings,
        -- Calculate cost savings percentage
        CASE
            WHEN d.manual_cost_baseline > 0
            THEN ((d.manual_cost_baseline - d.operational_cost) / d.manual_cost_baseline) * 100
            ELSE 0
        END as cost_savings_percentage,
        -- Check if deal is orchestrated
        CASE
            WHEN d.orchestration_mode = 'orchestrated' THEN 1
            ELSE 0
        END as is_orchestrated,
        -- Check if deal is manual
        CASE
            WHEN d.orchestration_mode = 'manual' THEN 1
            ELSE 0
        END as is_manual,
        -- Calculate potential acceleration value
        CASE
            WHEN d.orchestration_mode = 'orchestrated'
                 AND d.quote_generated_at IS NOT NULL
                 AND d.payment_collected_at IS NOT NULL
            THEN
                CASE
                    WHEN EXTRACT(EPOCH FROM (d.payment_collected_at - d.quote_generated_at)) / 3600 < 48
                    THEN d.amount * 0.1 * (1 - (EXTRACT(EPOCH FROM (d.payment_collected_at - d.quote_generated_at)) / 3600 / 48))
                    ELSE 0
                END
            ELSE 0
        END as acceleration_value
    FROM deals d
    WHERE d.amount IS NOT NULL;
    """)

    # Create summary view for quick dashboard metrics
    op.execute("""
    CREATE OR REPLACE VIEW v_sla_dashboard_summary AS
    SELECT
        -- Touch rate metrics
        COUNT(*) as total_deals,
        COUNT(CASE WHEN touched_within_5min AND quote_during_business_hours THEN 1 END) as business_deals_touched_5min,
        COUNT(CASE WHEN quote_during_business_hours THEN 1 END) as total_business_hour_deals,
        ROUND(
            COUNT(CASE WHEN touched_within_5min AND quote_during_business_hours THEN 1 END) * 100.0 /
            NULLIF(COUNT(CASE WHEN quote_during_business_hours THEN 1 END), 0), 2
        ) as touch_rate_percentage,

        -- Quote-to-cash metrics
        COUNT(CASE WHEN quote_to_cash_hours IS NOT NULL THEN 1 END) as completed_deals,
        ROUND(
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quote_to_cash_hours), 2
        ) as median_quote_to_cash_hours,
        ROUND(
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY quote_to_cash_hours), 2
        ) as p75_quote_to_cash_hours,
        ROUND(
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY quote_to_cash_hours), 2
        ) as p90_quote_to_cash_hours,

        -- Target compliance
        COUNT(CASE WHEN quote_to_cash_hours <= 24 THEN 1 END) as within_24h_count,
        COUNT(CASE WHEN quote_to_cash_hours <= 48 THEN 1 END) as within_48h_count,

        -- Guardrail compliance
        COUNT(CASE WHEN guardrail_status = 'pass' THEN 1 END) as guardrail_passed_count,
        COUNT(CASE WHEN guardrail_status = 'violated' THEN 1 END) as guardrail_violated_count,
        COUNT(CASE WHEN guardrail_locked = true THEN 1 END) as guardrail_locked_count,
        ROUND(
            COUNT(CASE WHEN guardrail_status = 'pass' THEN 1 END) * 100.0 /
            NULLIF(COUNT(*), 0), 2
        ) as guardrail_compliance_percentage,

        -- Financial metrics
        COALESCE(SUM(amount), 0) as total_revenue,
        COALESCE(SUM(operational_cost), 0) as total_operational_cost,
        COALESCE(SUM(cost_savings), 0) as total_cost_savings,
        COALESCE(SUM(acceleration_value), 0) as total_acceleration_value,

        -- Date range
        MIN(created_at) as earliest_deal,
        MAX(created_at) as latest_deal

    FROM v_deal_lifecycle_metrics dlm
    LEFT JOIN v_financial_impact_metrics fim ON dlm.id = fim.id;
    """)

    # Create indexes for better query performance
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_deals_quote_generated_at ON deals(quote_generated_at);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_deals_payment_collected_at ON deals(payment_collected_at);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_deals_guardrail_status ON deals(guardrail_status);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_deals_orchestration_mode ON deals(orchestration_mode);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at);
    """)


def downgrade() -> None:
    """Remove SLA analytics views and indexes."""

    # Drop views
    op.execute("DROP VIEW IF EXISTS v_sla_dashboard_summary;")
    op.execute("DROP VIEW IF EXISTS v_financial_impact_metrics;")
    op.execute("DROP VIEW IF EXISTS v_guardrail_compliance_metrics;")
    op.execute("DROP VIEW IF EXISTS v_payment_error_metrics;")
    op.execute("DROP VIEW IF EXISTS v_deal_lifecycle_metrics;")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_payments_created_at;")
    op.execute("DROP INDEX IF EXISTS idx_payments_status;")
    op.execute("DROP INDEX IF EXISTS idx_deals_orchestration_mode;")
    op.execute("DROP INDEX IF EXISTS idx_deals_guardrail_status;")
    op.execute("DROP INDEX IF EXISTS idx_deals_payment_collected_at;")
    op.execute("DROP INDEX IF EXISTS idx_deals_quote_generated_at;")