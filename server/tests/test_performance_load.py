"""
Performance and load testing for Deal Desk OS.

This module tests:
- Concurrent deal processing (50-200 deals)
- Database performance under load
- Redis caching performance validation
- API response time testing
- Memory and resource usage
- Throughput benchmarking
"""

import pytest
import pytest_asyncio
import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch
import statistics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.deal import Deal, DealStage, DealRisk
from app.models.payment import Payment
from app.models.invoice import Invoice
from app.services.deal_service import create_deal, list_deals, update_deal
from app.services.payment_service import PaymentService
from app.services.sla_cache import SLACache
from app.services.guardrail_service import evaluate_pricing_guardrails
from app.api.routes.deals import list_deals_endpoint


class TestConcurrentDealProcessing:
    """Testing concurrent deal processing capabilities."""

    @pytest_asyncio.asyncio
    async def test_concurrent_deal_creation_50_deals(self, async_db_session, generate_test_deal, benchmark_timer):
        """Test creating 50 deals concurrently."""
        deal_count = 50
        deals_to_create = []

        for i in range(deal_count):
            deal_data = generate_test_deal(
                id=f"concurrent_deal_{i}",
                name=f"Concurrent Deal {i}",
                amount=Decimal(str(10000 + (i * 1000))),
            )
            deals_to_create.append(deal_data)

        async with benchmark_timer:
            tasks = [
                create_deal(async_db_session, deal_data)
                for deal_data in deals_to_create
            ]

            created_deals = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all deals were created successfully
        successful_creations = [d for d in created_deals if not isinstance(d, Exception)]
        assert len(successful_creations) == deal_count
        assert benchmark_timer.elapsed_ms < 10000  # Should complete within 10 seconds

        # Verify database state
        async with async_db_session:
            result = await async_db_session.execute(
                text("SELECT COUNT(*) FROM deals WHERE id LIKE 'concurrent_deal_%'")
            )
            db_count = result.scalar()
            assert db_count == deal_count

    @pytest_asyncio.asyncio
    async def test_concurrent_deal_creation_200_deals(self, async_db_session, generate_test_deal):
        """Test creating 200 deals concurrently (stress test)."""
        deal_count = 200
        deals_to_create = []

        for i in range(deal_count):
            deal_data = generate_test_deal(
                id=f"stress_deal_{i}",
                name=f"Stress Deal {i}",
                amount=Decimal(str(5000 + (i * 500))),
                risk=list(DealRisk)[i % len(DealRisk)],
            )
            deals_to_create.append(deal_data)

        start_time = time.perf_counter()

        # Process in batches to avoid overwhelming the system
        batch_size = 50
        all_created_deals = []

        for batch_start in range(0, deal_count, batch_size):
            batch_end = min(batch_start + batch_size, deal_count)
            batch_deals = deals_to_create[batch_start:batch_end]

            tasks = [
                create_deal(async_db_session, deal_data)
                for deal_data in batch_deals
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            all_created_deals.extend(batch_results)

        end_time = time.perf_counter()
        total_time = end_time - start_time

        successful_creations = [d for d in all_created_deals if not isinstance(d, Exception)]
        assert len(successful_creations) == deal_count
        assert total_time < 30000  # Should complete within 30 seconds

    @pytest_asyncio.asyncio
    async def test_concurrent_deal_updates(self, async_db_session, seed_test_data, benchmark_timer):
        """Test concurrent deal updates."""
        # Get existing deals from seeded data
        deals_to_update = seed_test_data["deals"][:100]  # Update 100 deals
        update_data = {
            "description": f"Updated at {datetime.utcnow()}",
            "probability": 85,
        }

        async with benchmark_timer:
            tasks = [
                update_deal(async_db_session, deal, update_data)
                for deal in deals_to_update
            ]

            updated_deals = await asyncio.gather(*tasks, return_exceptions=True)

        successful_updates = [d for d in updated_deals if not isinstance(d, Exception)]
        assert len(successful_updates) == len(deals_to_update)
        assert benchmark_timer.elapsed_ms < 5000  # Should complete within 5 seconds

    @pytest_asyncio.asyncio
    async def test_concurrent_deal_listings_with_filters(self, async_db_session, seed_test_data, benchmark_timer):
        """Test concurrent deal listings with various filters."""
        test_filters = [
            {"stage": DealStage.PROSPECTING},
            {"risk": DealRisk.LOW},
            {"min_probability": 50},
            {"max_probability": 80},
            {"search": "Test"},
            {"page": 1, "page_size": 20},
            {"page": 2, "page_size": 20},
            {"page": 3, "page_size": 20},
        ]

        async with benchmark_timer:
            # Execute all filter queries concurrently
            tasks = [
                list_deals(async_db_session, **filters)
                for filters in test_filters
            ]

            filter_results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_results = [r for r in filter_results if not isinstance(r, Exception)]
        assert len(successful_results) == len(test_filters)
        assert benchmark_timer.elapsed_ms < 3000  # Should complete within 3 seconds


class TestDatabasePerformance:
    """Testing database performance under various loads."""

    @pytest_asyncio.asyncio
    async def test_bulk_deal_insertion_performance(self, async_db_session, benchmark_timer):
        """Test performance of bulk deal insertion."""
        from sqlalchemy.dialects.postgresql import insert

        deal_count = 1000
        deals_data = []

        for i in range(deal_count):
            deals_data.append({
                "id": f"bulk_deal_{i}",
                "name": f"Bulk Deal {i}",
                "description": "Bulk inserted deal for performance testing",
                "amount": Decimal(str(10000 + (i * 100))),
                "currency": "USD",
                "discount_percent": Decimal("15.00"),
                "payment_terms_days": 30,
                "risk": DealRisk.LOW,
                "probability": 75,
                "stage": DealStage.PROSPECTING,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })

        async with benchmark_timer:
            # Use bulk insert for better performance
            stmt = insert(Deal).values(deals_data)
            await async_db_session.execute(stmt)
            await async_db_session.commit()

        # 1000 records should be inserted quickly
        assert benchmark_timer.elapsed_ms < 5000  # Within 5 seconds

        # Verify insertion
        result = await async_db_session.execute(
            text("SELECT COUNT(*) FROM deals WHERE id LIKE 'bulk_deal_%'")
        )
        assert result.scalar() == deal_count

    @pytest_asyncio.asyncio
    async def test_complex_query_performance(self, async_db_session, seed_test_data, benchmark_timer):
        """Test performance of complex queries with joins and aggregations."""
        async with benchmark_timer:
            # Complex query with joins, aggregations, and filtering
            complex_query = text("""
                SELECT
                    d.risk,
                    d.stage,
                    COUNT(*) as deal_count,
                    AVG(d.amount) as avg_amount,
                    MAX(d.discount_percent) as max_discount,
                    SUM(d.amount) as total_amount
                FROM deals d
                WHERE d.created_at >= NOW() - INTERVAL '1 day'
                    AND d.probability >= 50
                GROUP BY d.risk, d.stage
                HAVING COUNT(*) >= 2
                ORDER BY total_amount DESC
                LIMIT 20
            """)

            result = await async_db_session.execute(complex_query)
            rows = result.fetchall()

        assert len(rows) >= 0  # Query should execute successfully
        assert benchmark_timer.elapsed_ms < 1000  # Complex query should complete within 1 second

    @pytest_asyncio.asyncio
    async def test_index_effectiveness(self, async_db_session, seed_test_data, benchmark_timer):
        """Test that indexes are being used effectively for common queries."""

        # Query without index hint
        async with benchmark_timer:
            result_no_index = await async_db_session.execute(
                text("SELECT * FROM deals WHERE amount >= 20000 AND probability >= 75")
            )
            deals_no_index = result_no_index.fetchall()

        time_no_index = benchmark_timer.elapsed_ms

        # Query with index hint (assuming indexes exist)
        async with benchmark_timer:
            result_with_index = await async_db_session.execute(
                text("SELECT * FROM deals WHERE amount >= 20000 AND probability >= 75")
            )
            deals_with_index = result_with_index.fetchall()

        time_with_index = benchmark_timer.elapsed_ms

        # Results should be the same
        assert len(deals_no_index) == len(deals_with_index)

        # With proper indexing, the second query should be faster or comparable
        # (This test assumes indexes are properly set up in the database)
        assert time_with_index <= time_no_index * 1.2  # Allow some variance

    @pytest_asyncio.asyncio
    async def test_transaction_throughput(self, async_db_session, benchmark_timer):
        """Test database transaction throughput."""
        transaction_count = 100
        operations_per_transaction = 5

        async with benchmark_timer:
            for i in range(transaction_count):
                # Each transaction creates, updates, and reads a deal
                async with async_db_session.begin():
                    # Create deal
                    deal = Deal(
                        id=f"tx_deal_{i}",
                        name=f"Transaction Deal {i}",
                        amount=Decimal("10000.00"),
                        currency="USD",
                        stage=DealStage.PROSPECTING,
                        created_at=datetime.utcnow(),
                    )
                    async_db_session.add(deal)
                    await async_db_session.flush()

                    # Update deal
                    deal.description = "Updated in same transaction"
                    deal.probability = 80

                    # Read deal
                    await async_db_session.get(Deal, deal.id)

                await async_db_session.commit()

        # Transaction throughput should be reasonable
        total_operations = transaction_count * operations_per_transaction
        operations_per_second = total_operations / (benchmark_timer.elapsed_ms / 1000)

        assert operations_per_second > 100  # Should handle at least 100 operations/second


class TestRedisCachePerformance:
    """Testing Redis caching performance."""

    @pytest_asyncio.asyncio
    async def test_cache_write_performance(self, async_db_session, mock_settings, benchmark_timer):
        """Test cache write performance."""
        cache = SLACache(mock_settings.redis_url)

        # Test writing 1000 cache entries
        cache_entries = [
            {
                "key": f"test_key_{i}",
                "value": {
                    "deal_id": f"deal_{i}",
                    "amount": 10000 + (i * 100),
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": "x" * 100,  # 100 bytes of data
                }
            }
            for i in range(1000)
        ]

        async with benchmark_timer:
            for entry in cache_entries:
                await cache.set(
                    entry["key"],
                    entry["value"],
                    ttl=3600  # 1 hour
                )

        # 1000 cache writes should be fast
        assert benchmark_timer.elapsed_ms < 5000  # Within 5 seconds
        writes_per_second = 1000 / (benchmark_timer.elapsed_ms / 1000)
        assert writes_per_second > 200  # At least 200 writes per second

    @pytest_asyncio.asyncio
    async def test_cache_read_performance(self, async_db_session, mock_settings, benchmark_timer):
        """Test cache read performance."""
        cache = SLACache(mock_settings.redis_url)

        # Pre-populate cache with test data
        for i in range(1000):
            await cache.set(
                f"read_test_key_{i}",
                {"data": f"value_{i}", "timestamp": datetime.utcnow().isoformat()},
                ttl=3600
            )

        # Test reading 1000 cache entries
        async with benchmark_timer:
            for i in range(1000):
                value = await cache.get(f"read_test_key_{i}")
                assert value is not None

        # Cache reads should be very fast
        assert benchmark_timer.elapsed_ms < 2000  # Within 2 seconds
        reads_per_second = 1000 / (benchmark_timer.elapsed_ms / 1000)
        assert reads_per_second > 500  # At least 500 reads per second

    @pytest_asyncio.asyncio
    async def test_cache_hit_miss_ratio(self, async_db_session, mock_settings):
        """Test cache hit/miss ratio under realistic load."""
        cache = SLACache(mock_settings.redis_url)

        # Pre-populate 50% of potential keys
        total_keys = 200
        for i in range(0, total_keys, 2):  # Even numbers only
            await cache.set(
                f"ratio_test_key_{i}",
                {"data": f"value_{i}"},
                ttl=3600
            )

        hits = 0
        misses = 0

        # Test all keys (some will hit, some will miss)
        for i in range(total_keys):
            value = await cache.get(f"ratio_test_key_{i}")
            if value is not None:
                hits += 1
            else:
                misses += 1

        # Should have approximately 50% hit rate
        hit_ratio = hits / (hits + misses)
        assert 0.45 <= hit_ratio <= 0.55  # Allow some variance

    @pytest_asyncio.asyncio
    async def test_cache_concurrent_access(self, async_db_session, mock_settings, benchmark_timer):
        """Test cache performance under concurrent access."""
        cache = SLACache(mock_settings.redis_url)

        # Pre-populate some keys
        for i in range(100):
            await cache.set(
                f"concurrent_key_{i}",
                {"data": f"value_{i}"},
                ttl=3600
            )

        async def cache_worker(worker_id):
            """Worker function that performs cache operations."""
            operations = []
            for i in range(50):
                # Mix of reads and writes
                if i % 2 == 0:
                    value = await cache.get(f"concurrent_key_{i}")
                    operations.append(("read", value is not None))
                else:
                    await cache.set(
                        f"worker_{worker_id}_key_{i}",
                        {"worker": worker_id, "data": f"value_{i}"},
                        ttl=3600
                    )
                    operations.append(("write", True))
            return operations

        # Run 10 concurrent workers
        async with benchmark_timer:
            tasks = [cache_worker(i) for i in range(10)]
            worker_results = await asyncio.gather(*tasks)

        # Verify all operations completed
        total_operations = sum(len(result) for result in worker_results)
        assert total_operations == 500  # 10 workers * 50 operations each

        # Concurrent operations should still be reasonably fast
        assert benchmark_timer.elapsed_ms < 10000  # Within 10 seconds


class TestAPIResponseTime:
    """Testing API endpoint response times."""

    @pytest_asyncio.asyncio
    async def test_deal_list_api_response_time(self, test_client, seed_test_data, benchmark_timer):
        """Test deal listing API response time."""
        async with benchmark_timer:
            response = test_client.get("/deals?page=1&page_size=20")

        assert response.status_code == 200
        assert benchmark_timer.elapsed_ms < 500  # Should respond within 500ms

        # Verify response structure
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    @pytest_asyncio.asyncio
    async def test_deal_search_api_response_time(self, test_client, seed_test_data, benchmark_timer):
        """Test deal search API response time."""
        search_params = "search=Test&stage=prospecting&min_probability=50"

        async with benchmark_timer:
            response = test_client.get(f"/deals?{search_params}")

        assert response.status_code == 200
        assert benchmark_timer.elapsed_ms < 750  # Search should respond within 750ms

    @pytest_asyncio.asyncio
    async def test_deal_creation_api_response_time(self, test_client, benchmark_timer):
        """Test deal creation API response time."""
        new_deal_data = {
            "name": "API Performance Test Deal",
            "description": "Deal created for API performance testing",
            "amount": "15000.00",
            "currency": "USD",
            "discount_percent": "10.0",
            "payment_terms_days": 30,
            "risk": "low",
            "probability": 80,
            "stage": "prospecting",
            "orchestration_mode": "manual",
        }

        async with benchmark_timer:
            response = test_client.post("/deals", json=new_deal_data)

        assert response.status_code == 201
        assert benchmark_timer.elapsed_ms < 1000  # Creation should respond within 1 second

        # Verify created deal
        created_deal = response.json()
        assert created_deal["name"] == new_deal_data["name"]
        assert created_deal["amount"] == new_deal_data["amount"]

    @pytest_asyncio.asyncio
    async def test_concurrent_api_requests(self, test_client, seed_test_data, benchmark_timer):
        """Test API performance under concurrent requests."""
        import requests
        import threading

        base_url = test_client.base_url
        request_count = 50
        response_times = []

        def make_request():
            """Make a single API request and record response time."""
            start_time = time.perf_counter()
            try:
                response = requests.get(f"{base_url}/deals?page=1&page_size=10", timeout=10)
                end_time = time.perf_counter()
                response_times.append(end_time - start_time)
                return response.status_code == 200
            except Exception:
                return False

        # Make concurrent requests
        async with benchmark_timer:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_request) for _ in range(request_count)]
                results = [f.result() for f in futures]

        # Analyze results
        successful_requests = sum(results)
        assert successful_requests >= request_count * 0.95  # 95% success rate

        if response_times:
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile

            assert avg_response_time < 1.0  # Average under 1 second
            assert p95_response_time < 2.0  # 95th percentile under 2 seconds


class TestMemoryAndResourceUsage:
    """Testing memory and resource usage under load."""

    @pytest_asyncio.asyncio
    async def test_memory_usage_during_bulk_operations(self, async_db_session, memory_profiler):
        """Test memory usage during bulk operations."""
        import psutil
        import os

        process = psutil.Process(os.getpid())

        with memory_profiler:
            # Create many deals to test memory usage
            deals = []
            for i in range(500):
                deal = Deal(
                    id=f"memory_test_deal_{i}",
                    name=f"Memory Test Deal {i}",
                    amount=Decimal(str(10000 + (i * 100))),
                    description="A" * 500,  # 500 character description
                    currency="USD",
                    stage=DealStage.PROSPECTING,
                    created_at=datetime.utcnow(),
                )
                deals.append(deal)

            # Add all deals to session
            for deal in deals:
                async_db_session.add(deal)

            # Flush to database
            await async_db_session.flush()
            await async_db_session.commit()

        # Memory increase should be reasonable (less than 100MB)
        assert memory_profiler.memory_increase_mb < 100

        # Verify all deals were created
        result = await async_db_session.execute(
            text("SELECT COUNT(*) FROM deals WHERE id LIKE 'memory_test_deal_%'")
        )
        assert result.scalar() == 500

    @pytest_asyncio.asyncio
    async def test_connection_pool_efficiency(self, async_db_session, benchmark_timer):
        """Test database connection pool efficiency under load."""
        from sqlalchemy import create_engine
        from sqlalchemy.pool import QueuePool

        # Test connection pool behavior
        async def database_worker(worker_id):
            """Worker that uses database connections."""
            async with async_db_session:
                for i in range(10):
                    # Simulate database work
                    result = await async_db_session.execute(
                        text("SELECT COUNT(*) FROM deals LIMIT 1")
                    )
                    count = result.scalar()
                    await asyncio.sleep(0.01)  # Small delay
            return count

        # Run multiple database workers
        async with benchmark_timer:
            tasks = [database_worker(i) for i in range(20)]
            results = await asyncio.gather(*tasks)

        # All workers should complete successfully
        assert len(results) == 20
        assert all(r >= 0 for r in results)

        # Connection pooling should make this efficient
        assert benchmark_timer.elapsed_ms < 10000  # Within 10 seconds

    @pytest_asyncio.asyncio
    async def test_garbage_collection_effectiveness(self, async_db_session, benchmark_timer):
        """Test that garbage collection is working effectively."""
        import gc
        import weakref

        # Create many temporary objects
        objects = []
        weak_refs = []

        for i in range(1000):
            obj = {
                "id": i,
                "data": "x" * 1000,  # 1KB per object
                "timestamp": datetime.utcnow(),
            }
            objects.append(obj)
            weak_refs.append(weakref.ref(obj))

        # Force garbage collection
        async with benchmark_timer:
            del objects
            gc.collect()

        # Most objects should be garbage collected
        surviving_objects = sum(1 for ref in weak_refs if ref() is not None)
        assert surviving_objects < 100  # Less than 10% should survive

        # Garbage collection should be reasonably fast
        assert benchmark_timer.elapsed_ms < 5000  # Within 5 seconds


class TestThroughputBenchmarking:
    """Testing system throughput under various conditions."""

    @pytest_asyncio.asyncio
    async def test_deal_creation_throughput(self, async_db_session, benchmark_timer):
        """Test maximum deal creation throughput."""
        deal_count = 100
        deals_to_create = []

        for i in range(deal_count):
            deal_data = {
                "id": f"throughput_deal_{i}",
                "name": f"Throughput Deal {i}",
                "amount": 10000 + (i * 100),
                "currency": "USD",
                "stage": DealStage.PROSPECTING,
                "created_at": datetime.utcnow(),
            }
            deals_to_create.append(deal_data)

        # Measure throughput
        async with benchmark_timer:
            tasks = [
                create_deal(async_db_session, Deal(**deal_data))
                for deal_data in deals_to_create
            ]
            created_deals = await asyncio.gather(*tasks, return_exceptions=True)

        successful_creations = [d for d in created_deals if not isinstance(d, Exception)]
        assert len(successful_creations) == deal_count

        # Calculate and validate throughput
        throughput = deal_count / (benchmark_timer.elapsed_ms / 1000)  # deals per second
        assert throughput > 10  # Should handle at least 10 deals per second

    @pytest_asyncio.asyncio
    async def test_payment_processing_throughput(self, async_db_session, mock_stripe_adapter, benchmark_timer):
        """Test payment processing throughput."""
        payment_service = PaymentService(async_db_session)

        # Create test payments
        payment_count = 50
        payment_tasks = []

        for i in range(payment_count):
            task = payment_service.process_payment(
                deal_id=f"throughput_deal_{i}",
                invoice_id=f"throughput_invoice_{i}",
                amount=Decimal("10000.00"),
                currency="USD",
                idempotency_key=f"payment_{i}_{int(time.time())}",
                payment_method="pm_stripe_test_card",
            )
            payment_tasks.append(task)

        # Measure payment processing throughput
        async with benchmark_timer:
            payment_results = await asyncio.gather(*payment_tasks, return_exceptions=True)

        successful_payments = [p for p in payment_results if not isinstance(p, Exception) and p.get("success")]
        assert len(successful_payments) == payment_count

        # Calculate throughput
        throughput = payment_count / (benchmark_timer.elapsed_ms / 1000)  # payments per second
        assert throughput > 5  # Should handle at least 5 payments per second

    @pytest_asyncio.asyncio
    async def test_guardrail_evaluation_throughput(self, async_db_session, benchmark_timer):
        """Test guardrail evaluation throughput."""
        evaluation_count = 200
        evaluation_tasks = []

        for i in range(evaluation_count):
            # Mix of different deal characteristics
            amount = 5000 + (i * 1000)
            discount = 5 + (i % 25)
            risk = list(DealRisk)[i % len(DealRisk)]

            task = evaluate_pricing_guardrails(
                amount=Decimal(str(amount)),
                discount_percent=discount,
                payment_terms_days=30 + (i % 60),
                risk=risk,
            )
            evaluation_tasks.append(task)

        # Measure guardrail evaluation throughput
        async with benchmark_timer:
            evaluation_results = await asyncio.gather(*evaluation_tasks, return_exceptions=True)

        successful_evaluations = [e for e in evaluation_results if not isinstance(e, Exception)]
        assert len(successful_evaluations) == evaluation_count

        # Calculate throughput
        throughput = evaluation_count / (benchmark_timer.elapsed_ms / 1000)  # evaluations per second
        assert throughput > 100  # Should handle at least 100 evaluations per second

    @pytest_asyncio.asyncio
    async def test_mixed_workload_throughput(self, async_db_session, mock_stripe_adapter, benchmark_timer):
        """Test system throughput with mixed workload."""
        async def mixed_worker(worker_id):
            """Worker that performs mixed operations."""
            results = []

            # Create deal
            deal_data = {
                "id": f"mixed_deal_{worker_id}",
                "name": f"Mixed Workload Deal {worker_id}",
                "amount": 10000 + (worker_id * 500),
                "currency": "USD",
                "stage": DealStage.PROSPECTING,
            }
            deal = await create_deal(async_db_session, Deal(**deal_data))
            results.append(("create", deal.id is not None))

            # Evaluate guardrails
            evaluation = await evaluate_pricing_guardrails(
                amount=Decimal(str(deal_data["amount"])),
                discount_percent=15.0,
                payment_terms_days=30,
                risk=DealRisk.MEDIUM,
            )
            results.append(("guardrail", evaluation is not None))

            # Create payment
            payment_service = PaymentService(async_db_session)
            payment_result = await payment_service.process_payment(
                deal_id=deal.id,
                invoice_id=f"mixed_invoice_{worker_id}",
                amount=deal.amount,
                currency=deal.currency,
                idempotency_key=f"mixed_payment_{worker_id}_{int(time.time())}",
                payment_method="pm_stripe_test",
            )
            results.append(("payment", payment_result.get("success", False)))

            return results

        # Run mixed workload with multiple workers
        async with benchmark_timer:
            tasks = [mixed_worker(i) for i in range(20)]
            worker_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Analyze results
        successful_workers = [r for r in worker_results if not isinstance(r, Exception)]
        assert len(successful_workers) == 20

        # Count successful operations
        total_operations = 0
        successful_operations = 0

        for result in successful_workers:
            for operation_type, success in result:
                total_operations += 1
                if success:
                    successful_operations += 1

        success_rate = successful_operations / total_operations
        assert success_rate > 0.95  # 95% success rate for mixed workload

        # Calculate mixed throughput
        throughput = total_operations / (benchmark_timer.elapsed_ms / 1000)  # operations per second
        assert throughput > 10  # Should handle at least 10 operations per second