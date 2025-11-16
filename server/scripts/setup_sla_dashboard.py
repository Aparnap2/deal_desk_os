#!/usr/bin/env python3
"""
Setup script for SLA Dashboard functionality.

This script sets up the SLA dashboard by:
1. Running database migrations for SLA views
2. Creating necessary indexes
3. Verifying configuration
4. Running initial health checks
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger, configure_logging
from app.services.sla_analytics import SLAAnalyticsService
from app.services.sla_cache import SLACacheService
from app.core.sla_settings import get_sla_settings

logger = get_logger(__name__)


class SLADashboardSetup:
    """SLA Dashboard setup and initialization."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.sla_settings = get_sla_settings()
        self.engine = None

    async def setup_database(self):
        """Set up database with SLA views and indexes."""
        logger.info("Setting up SLA dashboard database views and indexes")

        try:
            # Create async engine
            self.engine = create_async_engine(
                self.settings.database_url,
                echo=False
            )

            async with self.engine.begin() as conn:
                # Check if deals table exists
                result = await conn.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'deals')")
                )
                deals_exists = result.scalar()

                if not deals_exists:
                    logger.error("Deals table not found. Please run main migrations first.")
                    return False

                # Create SLA views
                await self._create_sla_views(conn)

                # Create indexes
                await self._create_sla_indexes(conn)

                # Verify setup
                await self._verify_setup(conn)

            logger.info("SLA dashboard database setup completed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to set up SLA dashboard database: {e}", exc_info=True)
            return False
        finally:
            if self.engine:
                await self.engine.dispose()

    async def _create_sla_views(self, conn):
        """Create SLA analytics views."""
        logger.info("Creating SLA analytics views")

        # Deal lifecycle metrics view
        await conn.execute(text("""
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
        """))

        # Payment error metrics view
        await conn.execute(text("""
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
        """))

        logger.info("SLA views created successfully")

    async def _create_sla_indexes(self, conn):
        """Create performance indexes for SLA queries."""
        logger.info("Creating SLA performance indexes")

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_deals_quote_generated_at ON deals(quote_generated_at);",
            "CREATE INDEX IF NOT EXISTS idx_deals_payment_collected_at ON deals(payment_collected_at);",
            "CREATE INDEX IF NOT EXISTS idx_deals_guardrail_status ON deals(guardrail_status);",
            "CREATE INDEX IF NOT EXISTS idx_deals_orchestration_mode ON deals(orchestration_mode);",
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);",
            "CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_deals_created_at ON deals(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage);"
        ]

        for index_sql in indexes:
            await conn.execute(text(index_sql))

        logger.info(f"Created {len(indexes)} performance indexes")

    async def _verify_setup(self, conn):
        """Verify that SLA setup is working correctly."""
        logger.info("Verifying SLA dashboard setup")

        # Check views exist
        views = ["v_deal_lifecycle_metrics", "v_payment_error_metrics"]
        for view in views:
            result = await conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.views WHERE table_name = :view_name)"
            ), {"view_name": view})
            exists = result.scalar()
            if not exists:
                raise Exception(f"View {view} was not created")
            logger.info(f"View {view} verified")

        # Check indexes exist (basic check)
        result = await conn.execute(text("""
            SELECT count(*) FROM pg_indexes
            WHERE indexname LIKE 'idx_%_sla_%' OR indexname LIKE 'idx_deals_%' OR indexname LIKE 'idx_payments_%'
        """))
        index_count = result.scalar()
        logger.info(f"Verified {index_count} performance indexes")

        # Test basic query
        result = await conn.execute(text("SELECT COUNT(*) FROM v_deal_lifecycle_metrics LIMIT 1"))
        count = result.scalar()
        logger.info(f"Test query executed successfully, found {count} records in lifecycle view")

    async def verify_configuration(self):
        """Verify SLA configuration is valid."""
        logger.info("Verifying SLA configuration")

        try:
            # Test database connection
            self.engine = create_async_engine(self.settings.database_url)
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection verified")

            # Test Redis connection (if configured)
            if self.settings.redis_url:
                cache_service = SLACacheService()
                redis_client = cache_service._get_redis_client()
                if redis_client:
                    redis_client.ping()
                    logger.info("Redis connection verified")
                else:
                    logger.warning("Redis connection failed - caching will be disabled")
            else:
                logger.info("Redis not configured - caching disabled")

            # Test SLA settings
            sla_targets = self.sla_settings.get_sla_targets()
            logger.info(f"SLA targets configured: {list(sla_targets.keys())}")

            # Test business hours configuration
            workdays = self.sla_settings.get_workdays_list()
            logger.info(f"Business hours configured: {self.sla_settings.business_hours_start}:00-{self.sla_settings.business_hours_end}:00, workdays: {workdays}")

            logger.info("SLA configuration verified successfully")
            return True

        except Exception as e:
            logger.error(f"SLA configuration verification failed: {e}", exc_info=True)
            return False
        finally:
            if self.engine:
                await self.engine.dispose()

    async def run_health_checks(self):
        """Run health checks for SLA dashboard services."""
        logger.info("Running SLA dashboard health checks")

        try:
            # Test SLA analytics service
            analytics_service = SLAAnalyticsService()
            # Note: We can't fully test without data, but we can verify the service instantiates correctly
            logger.info("SLA analytics service initialized")

            # Test cache service
            cache_service = SLACacheService()
            cache_info = await cache_service.get_cache_info()
            logger.info(f"Cache service status: {cache_info.get('status', 'unknown')}")

            logger.info("SLA dashboard health checks completed")
            return True

        except Exception as e:
            logger.error(f"SLA dashboard health checks failed: {e}", exc_info=True)
            return False

    async def setup_all(self, skip_db_setup=False):
        """Run complete SLA dashboard setup."""
        logger.info("Starting SLA dashboard setup")
        start_time = datetime.utcnow()

        try:
            # Step 1: Verify configuration
            if not await self.verify_configuration():
                return False

            # Step 2: Setup database (if not skipped)
            if not skip_db_setup:
                if not await self.setup_database():
                    return False
            else:
                logger.info("Skipping database setup as requested")

            # Step 3: Run health checks
            if not await self.run_health_checks():
                return False

            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"SLA dashboard setup completed successfully in {duration:.2f} seconds")
            return True

        except Exception as e:
            logger.error(f"SLA dashboard setup failed: {e}", exc_info=True)
            return False


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Setup SLA Dashboard for Deal Desk OS")
    parser.add_argument(
        "--skip-db-setup",
        action="store_true",
        help="Skip database setup (useful if already done via migrations)"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run verification checks, don't modify anything"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level"
    )

    args = parser.parse_args()

    # Configure logging
    configure_logging()
    logger.setLevel(args.log_level)

    # Initialize setup
    setup = SLADashboardSetup()

    if args.verify_only:
        logger.info("Running verification-only mode")
        success = await setup.verify_configuration()
        if success:
            success = await setup.run_health_checks()
    else:
        success = await setup.setup_all(skip_db_setup=args.skip_db_setup)

    if success:
        logger.info("SLA Dashboard setup completed successfully! 🎉")
        print("\n" + "="*60)
        print("🚀 SLA Dashboard Setup Complete!")
        print("="*60)
        print("\nDashboard endpoints are now available at:")
        print("  • GET /sla-dashboard/summary - Complete dashboard")
        print("  • GET /sla-dashboard/touch-rate - Five-minute touch rate")
        print("  • GET /sla-dashboard/quote-to-cash - Quote-to-cash metrics")
        print("  • GET /sla-dashboard/error-rate - Error rate analysis")
        print("  • GET /sla-dashboard/guardrail-compliance - Guardrail compliance")
        print("  • GET /sla-dashboard/financial-impact - Financial impact")
        print("  • GET /sla-dashboard/sla-status - Overall SLA status")
        print("  • GET /sla-dashboard/metrics/export - Export metrics")
        print("  • GET /sla-dashboard/health - Service health")
        print("\nNext steps:")
        print("  1. Start your application server")
        print("  2. Visit the dashboard endpoints with authentication")
        print("  3. Monitor your SLA metrics in real-time!")
        print("="*60)
        sys.exit(0)
    else:
        logger.error("SLA Dashboard setup failed")
        print("\n❌ SLA Dashboard setup failed. Check the logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())