"""
Production Security Middleware for AP/AR Working-Capital Copilot
"""

import time
from typing import Callable

from fastapi import Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS (only in production with HTTPS)
        if request.url.scheme == "https":
            response.headers[
                "Strict-Transport-Security"
            ] = "max-age=31536000; includeSubDomains; preload"

        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.stripe.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware."""

    def __init__(
        self,
        app,
        calls: int = 100,
        period: int = 60,
        block_duration: int = 300,
    ):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.block_duration = block_duration
        self.clients = {}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Get client IP
        client_ip = self._get_client_ip(request)

        # Check rate limit
        current_time = time.time()

        if client_ip in self.clients:
            client_data = self.clients[client_ip]

            # Check if client is currently blocked
            if client_data.get("blocked_until", 0) > current_time:
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "client_ip": client_ip,
                        "blocked_until": client_data["blocked_until"],
                    },
                )
                return Response(
                    content="Rate limit exceeded. Please try again later.",
                    status_code=429,
                    headers={"Retry-After": str(self.block_duration)},
                )

            # Clean old requests
            client_data["requests"] = [
                req_time for req_time in client_data["requests"]
                if current_time - req_time < self.period
            ]

            # Check rate limit
            if len(client_data["requests"]) >= self.calls:
                client_data["blocked_until"] = current_time + self.block_duration
                logger.warning(
                    "Rate limit exceeded - client blocked",
                    extra={
                        "client_ip": client_ip,
                        "requests_count": len(client_data["requests"]),
                        "blocked_until": client_data["blocked_until"],
                    },
                )
                return Response(
                    content="Rate limit exceeded. Please try again later.",
                    status_code=429,
                    headers={"Retry-After": str(self.block_duration)},
                )

            client_data["requests"].append(current_time)
        else:
            self.clients[client_ip] = {"requests": [current_time]}

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining_requests = max(0, self.calls - len(self.clients[client_ip]["requests"]))
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(remaining_requests)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + self.period))

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded header first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to client host
        return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests with security context."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.time()

        # Log request
        logger.info(
            "HTTP request started",
            extra={
                "method": request.method,
                "url": str(request.url),
                "client_ip": self._get_client_ip(request),
                "user_agent": request.headers.get("User-Agent", ""),
                "content_length": request.headers.get("Content-Length", "0"),
            },
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate processing time
            process_time = time.time() - start_time

            # Log response
            logger.info(
                "HTTP request completed",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "client_ip": self._get_client_ip(request),
                    "status_code": response.status_code,
                    "process_time": f"{process_time:.4f}",
                },
            )

            # Add processing time header
            response.headers["X-Process-Time"] = f"{process_time:.4f}"

            return response

        except Exception as e:
            process_time = time.time() - start_time

            # Log error
            logger.error(
                "HTTP request failed",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "client_ip": self._get_client_ip(request),
                    "error": str(e),
                    "process_time": f"{process_time:.4f}",
                },
                exc_info=True,
            )

            raise

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"


class SizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request size based on endpoint."""

    def __init__(self, app, max_size: int = 50 * 1024 * 1024):  # 50MB default
        super().__init__(app)
        self.max_size = max_size
        self.upload_endpoints = {"/ap/intake", "/ap/upload"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Check content length for upload endpoints
        if request.url.path in self.upload_endpoints:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                logger.warning(
                    "Request too large",
                    extra={
                        "client_ip": self._get_client_ip(request),
                        "content_length": content_length,
                        "max_size": self.max_size,
                        "path": request.url.path,
                    },
                )
                return Response(
                    content=f"Request too large. Maximum size is {self.max_size // (1024*1024)}MB",
                    status_code=413,
                )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"