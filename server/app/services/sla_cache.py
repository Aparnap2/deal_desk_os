"""
SLA metrics caching service using Redis.

This module provides intelligent caching for SLA calculations to improve
dashboard performance and reduce database load.
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class SLACacheService:
    """Service for caching SLA metrics in Redis."""

    def __init__(self):
        self.redis_url = settings.redis_url
        self.default_ttl = 300  # 5 minutes
        self.key_prefix = "sla_dashboard"

    def _get_redis_client(self):
        """Get Redis client connection."""
        try:
            import redis
            return redis.from_url(self.redis_url, decode_responses=True)
        except ImportError:
            logger.warning("Redis not available, caching disabled")
            return None
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None

    def _generate_cache_key(
        self,
        metric_type: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        **kwargs
    ) -> str:
        """Generate a unique cache key for the metric calculation."""
        # Create a hash of all parameters to ensure uniqueness
        params = {
            "metric_type": metric_type,
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
            **kwargs
        }

        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:16]

        return f"{self.key_prefix}:{metric_type}:{params_hash}"

    async def get_cached_metrics(
        self,
        metric_type: str,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached SLA metrics if available and not expired.

        Args:
            metric_type: Type of metric (e.g., "touch_rate", "quote_to_cash")
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            **kwargs: Additional parameters for cache key generation

        Returns:
            Cached metrics data or None if not found/expired
        """
        cache_key = self._generate_cache_key(metric_type, start_date, end_date, **kwargs)
        redis_client = self._get_redis_client()

        if not redis_client:
            return None

        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {metric_type}", extra={"cache_key": cache_key})
                return json.loads(cached_data)
            else:
                logger.debug(f"Cache miss for {metric_type}", extra={"cache_key": cache_key})
                return None
        except Exception as e:
            logger.warning(f"Failed to get cached metrics: {e}", extra={"cache_key": cache_key})
            return None

    async def cache_metrics(
        self,
        metric_type: str,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        **kwargs
    ) -> bool:
        """
        Cache SLA metrics data.

        Args:
            metric_type: Type of metric being cached
            data: Metrics data to cache
            ttl: Time-to-live in seconds (uses default if None)
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            **kwargs: Additional parameters for cache key generation

        Returns:
            True if caching succeeded, False otherwise
        """
        cache_key = self._generate_cache_key(metric_type, start_date, end_date, **kwargs)
        redis_client = self._get_redis_client()

        if not redis_client:
            return False

        try:
            # Add cache metadata
            cache_data = {
                "data": data,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl or self.default_ttl,
                "metric_type": metric_type,
                "parameters": {
                    "start_date": str(start_date) if start_date else None,
                    "end_date": str(end_date) if end_date else None,
                    **kwargs
                }
            }

            # Store with expiration
            ttl = ttl or self.default_ttl
            redis_client.setex(cache_key, ttl, json.dumps(cache_data))

            logger.debug(f"Cached {metric_type} metrics", extra={
                "cache_key": cache_key,
                "ttl": ttl
            })

            return True
        except Exception as e:
            logger.warning(f"Failed to cache metrics: {e}", extra={"cache_key": cache_key})
            return False

    async def invalidate_cache(
        self,
        metric_type: Optional[str] = None,
        pattern: Optional[str] = None
    ) -> int:
        """
        Invalidate cached metrics.

        Args:
            metric_type: Specific metric type to invalidate
            pattern: Redis pattern for bulk invalidation

        Returns:
            Number of cache keys invalidated
        """
        redis_client = self._get_redis_client()

        if not redis_client:
            return 0

        try:
            if metric_type:
                # Invalidate specific metric type
                pattern = f"{self.key_prefix}:{metric_type}:*"
            elif pattern:
                # Use provided pattern
                pass
            else:
                # Invalidate all SLA dashboard cache
                pattern = f"{self.key_prefix}:*"

            keys = redis_client.keys(pattern)
            if keys:
                deleted = redis_client.delete(*keys)
                logger.info(f"Invalidated {deleted} cache keys", extra={
                    "pattern": pattern,
                    "keys_count": len(keys)
                })
                return deleted
            else:
                logger.debug("No cache keys found to invalidate", extra={"pattern": pattern})
                return 0
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")
            return 0

    async def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about cached metrics.

        Returns:
            Cache statistics and information
        """
        redis_client = self._get_redis_client()

        if not redis_client:
            return {"status": "unavailable", "message": "Redis not available"}

        try:
            # Get all SLA dashboard cache keys
            pattern = f"{self.key_prefix}:*"
            keys = redis_client.keys(pattern)

            # Analyze cache keys
            metric_types = {}
            total_size = 0
            oldest_cache = None
            newest_cache = None

            for key in keys:
                try:
                    cached_data = redis_client.get(key)
                    if cached_data:
                        data = json.loads(cached_data)
                        metric_type = data.get("metric_type", "unknown")
                        cached_at = data.get("cached_at")

                        metric_types[metric_type] = metric_types.get(metric_type, 0) + 1
                        total_size += len(cached_data)

                        if cached_at:
                            cached_dt = datetime.fromisoformat(cached_at.replace('Z', '+00:00'))
                            if oldest_cache is None or cached_dt < oldest_cache:
                                oldest_cache = cached_dt
                            if newest_cache is None or cached_dt > newest_cache:
                                newest_cache = cached_dt
                except Exception as e:
                    logger.warning(f"Failed to analyze cache key {key}: {e}")

            return {
                "status": "available",
                "total_keys": len(keys),
                "metric_types": metric_types,
                "total_size_bytes": total_size,
                "oldest_cache": oldest_cache.isoformat() if oldest_cache else None,
                "newest_cache": newest_cache.isoformat() if newest_cache else None,
                "key_prefix": self.key_prefix
            }
        except Exception as e:
            logger.error(f"Failed to get cache info: {e}")
            return {"status": "error", "message": str(e)}

    async def warm_cache(self) -> Dict[str, bool]:
        """
        Warm up the cache with commonly accessed metrics.

        Returns:
            Dictionary indicating which metrics were successfully warmed
        """
        logger.info("Starting cache warmup")
        results = {}

        # This would typically call the actual SLA calculation methods
        # to pre-populate the cache with common date ranges
        # For now, we'll just log the intention
        common_metrics = [
            "touch_rate",
            "quote_to_cash",
            "error_rate",
            "guardrail_compliance",
            "financial_impact"
        ]

        for metric in common_metrics:
            # Placeholder for actual cache warming logic
            results[metric] = False  # Would be True if successfully warmed
            logger.debug(f"Cache warmup scheduled for {metric}")

        logger.info("Cache warmup completed", extra={"results": results})
        return results

    async def get_cache_hit_rate(self) -> Dict[str, float]:
        """
        Get cache hit rate statistics.

        Returns:
            Cache hit rate by metric type
        """
        redis_client = self._get_redis_client()

        if not redis_client:
            return {}

        try:
            # In a real implementation, you would track hits/misses
            # This is a simplified version
            pattern = f"{self.key_prefix}:*"
            keys = redis_client.keys(pattern)

            # For now, return a simple count-based metric
            hit_rates = {}
            total_keys = len(keys)

            if total_keys > 0:
                # Assign a mock hit rate based on recency
                # In practice, you'd track actual hit/miss ratios
                hit_rates["overall"] = min(0.95, total_keys / 100)  # Mock calculation

            return hit_rates
        except Exception as e:
            logger.error(f"Failed to get cache hit rate: {e}")
            return {}


# Global cache service instance
cache_service = SLACacheService()


# Decorator for caching SLA calculations
def cache_sla_metrics(
    ttl: Optional[int] = None,
    key_params: Optional[List[str]] = None
):
    """
    Decorator to cache SLA calculation results.

    Args:
        ttl: Time-to-live in seconds
        key_params: List of parameter names to include in cache key
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract function name for cache key
            func_name = func.__name__

            # Build cache key parameters
            cache_kwargs = {}
            if key_params:
                for param in key_params:
                    if param in kwargs:
                        cache_kwargs[param] = kwargs[param]

            # Try to get from cache first
            cached_result = await cache_service.get_cached_metrics(
                metric_type=func_name,
                **cache_kwargs
            )

            if cached_result is not None:
                return cached_result["data"]

            # Execute function and cache result
            result = await func(*args, **kwargs)

            # Cache the result
            await cache_service.cache_metrics(
                metric_type=func_name,
                data=result,
                ttl=ttl,
                **cache_kwargs
            )

            return result

        return wrapper
    return decorator