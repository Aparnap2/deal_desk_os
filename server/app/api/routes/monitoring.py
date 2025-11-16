"""
Monitoring and health check endpoints for production deployment
"""

import asyncio
import psutil
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.dependencies.database import get_db
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])
settings = get_settings()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Comprehensive health check endpoint."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "checks": {},
    }

    # Database health check
    try:
        start_time = datetime.utcnow()
        await db.execute(text("SELECT 1"))
        db_response_time = (datetime.utcnow() - start_time).total_seconds()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "response_time": f"{db_response_time:.3f}s",
        }
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)}, exc_info=True)
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health_status["status"] = "unhealthy"

    # Redis health check (if configured)
    if settings.redis_url:
        try:
            import redis
            redis_client = redis.from_url(settings.redis_url)
            start_time = datetime.utcnow()
            redis_client.ping()
            redis_response_time = (datetime.utcnow() - start_time).total_seconds()
            health_status["checks"]["redis"] = {
                "status": "healthy",
                "response_time": f"{redis_response_time:.3f}s",
            }
        except Exception as e:
            logger.error("Redis health check failed", extra={"error": str(e)}, exc_info=True)
            health_status["checks"]["redis"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            health_status["status"] = "unhealthy"

    # System resource checks
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        health_status["checks"]["system"] = {
            "status": "healthy",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "memory_available": f"{memory.available / (1024**3):.1f}GB",
        }

        # Warn if resources are high
        if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
            health_status["checks"]["system"]["status"] = "warning"
            if health_status["status"] == "healthy":
                health_status["status"] = "warning"

    except Exception as e:
        logger.error("System health check failed", extra={"error": str(e)}, exc_info=True)
        health_status["checks"]["system"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        health_status["status"] = "unhealthy"

    # Determine overall status
    all_checks = list(health_status["checks"].values())
    if any(check["status"] == "unhealthy" for check in all_checks):
        health_status["status"] = "unhealthy"
    elif any(check["status"] == "warning" for check in all_checks):
        health_status["status"] = "warning"

    status_code = 200 if health_status["status"] == "healthy" else 503
    if health_status["status"] == "warning":
        status_code = 200  # Warning still returns 200

    raise HTTPException(status_code=status_code, detail=health_status)


@router.get("/readiness")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Readiness probe for Kubernetes/container orchestration."""
    readiness_status = {
        "ready": True,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }

    # Check database connection
    try:
        await db.execute(text("SELECT 1"))
        readiness_status["checks"]["database"] = "ready"
    except Exception as e:
        logger.warning("Readiness check: database not ready", extra={"error": str(e)})
        readiness_status["checks"]["database"] = "not_ready"
        readiness_status["ready"] = False

    # Check if application can accept traffic
    try:
        # Simple application logic check
        await db.execute(text("SELECT COUNT(*) FROM information_schema.tables"))
        readiness_status["checks"]["application"] = "ready"
    except Exception as e:
        logger.warning("Readiness check: application not ready", extra={"error": str(e)})
        readiness_status["checks"]["application"] = "not_ready"
        readiness_status["ready"] = False

    status_code = 200 if readiness_status["ready"] else 503
    raise HTTPException(status_code=status_code, detail=readiness_status)


@router.get("/liveness")
async def liveness_check() -> Dict[str, Any]:
    """Liveness probe for Kubernetes/container orchestration."""
    liveness_status = {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat(),
    }

    return liveness_status


@router.get("/metrics")
async def metrics_endpoint() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    metrics = []

    # System metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    metrics.append(f"cpu_usage_percent {cpu_percent}")
    metrics.append(f"memory_usage_percent {memory.percent}")
    metrics.append(f"memory_available_bytes {memory.available}")
    metrics.append(f"disk_usage_percent {disk.percent}")
    metrics.append(f"disk_available_bytes {disk.free}")

    # Process metrics
    process = psutil.Process()
    process_memory = process.memory_info()
    process_cpu = process.cpu_percent()

    metrics.append(f"process_memory_rss_bytes {process_memory.rss}")
    metrics.append(f"process_memory_vms_bytes {process_memory.vms}")
    metrics.append(f"process_cpu_percent {process_cpu}")

    # Application metrics (placeholder for custom metrics)
    metrics.append("# HELP http_requests_total Total number of HTTP requests")
    metrics.append("# TYPE http_requests_total counter")
    metrics.append("http_requests_total 0")

    metrics.append("# HELP http_request_duration_seconds HTTP request duration")
    metrics.append("# TYPE http_request_duration_seconds histogram")
    metrics.append("http_request_duration_seconds_bucket{le=\"0.1\"} 0")
    metrics.append("http_request_duration_seconds_bucket{le=\"+Inf\"} 0")

    return PlainTextResponse(content="\n".join(metrics), media_type="text/plain")


@router.get("/info")
async def application_info() -> Dict[str, Any]:
    """Application information endpoint."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "environment": settings.environment,
        "build_date": "2025-11-15T00:00:00Z",
        "git_commit": "unknown",
        "python_version": f"{psutil.sys.version_info.major}.{psutil.sys.version_info.minor}.{psutil.sys.version_info.micro}",
        "framework": "FastAPI",
        "database": "PostgreSQL",
        "cache": "Redis",
    }


@router.get("/status")
async def detailed_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Detailed status endpoint for monitoring."""
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": "0s",  # Would calculate actual uptime
        "system": {
            "cpu": {
                "usage_percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
            },
            "memory": {
                "total": f"{psutil.virtual_memory().total / (1024**3):.1f}GB",
                "available": f"{psutil.virtual_memory().available / (1024**3):.1f}GB",
                "used_percent": psutil.virtual_memory().percent,
            },
            "disk": {
                "total": f"{psutil.disk_usage('/').total / (1024**3):.1f}GB",
                "free": f"{psutil.disk_usage('/').free / (1024**3):.1f}GB",
                "used_percent": psutil.disk_usage('/').percent,
            },
        },
        "database": {
            "status": "unknown",
            "pool_size": "unknown",
        },
        "redis": {
            "status": "unknown",
            "memory_usage": "unknown",
        },
        "application": {
            "active_connections": 0,
            "requests_per_minute": 0,
        },
    }

    # Database status
    try:
        await db.execute(text("SELECT 1"))
        status["database"]["status"] = "connected"
    except Exception as e:
        status["database"]["status"] = f"error: {str(e)}"

    # Redis status
    if settings.redis_url:
        try:
            import redis
            redis_client = redis.from_url(settings.redis_url)
            info = redis_client.info()
            status["redis"]["status"] = "connected"
            status["redis"]["memory_usage"] = f"{info.get('used_memory', 0) / (1024**2):.1f}MB"
        except Exception as e:
            status["redis"]["status"] = f"error: {str(e)}"

    return status