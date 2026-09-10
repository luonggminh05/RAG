import logging
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)

# Public paths bypassing API key authentication
_PUBLIC_PATHS: set[str] = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    f"{settings.API_V1_STR}/health",
}

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host if request.client else "unknown"
        )
        logger.info("--> %s %s [client=%s]", request.method, request.url.path, client_ip)
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "<-- %s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        return response


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Pass CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Pass public paths & static UI assets
        if request.url.path in _PUBLIC_PATHS or request.url.path.startswith("/ui") or request.url.path.startswith("/static"):
            return await call_next(request)

        required_key = settings.effective_api_key
        if not required_key:
            return await call_next(request)

        # Check headers: X-Internal-Api-Key or X-API-Key or Authorization
        api_key = (
            request.headers.get("X-Internal-Api-Key")
            or request.headers.get("X-API-Key")
            or request.headers.get("x-api-key")
        )
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]

        if api_key != required_key:
            logger.warning(
                "[AUTH] Unauthorized request: %s %s", request.method, request.url.path
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing API key."},
            )

        return await call_next(request)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        if not getattr(settings, "rate_limit_enabled", False):
            return await call_next(request)

        path = request.url.path
        if (
            path in _PUBLIC_PATHS
            or path.startswith("/ui")
            or path.startswith("/static")
            or "/health" in path
        ):
            return await call_next(request)

        is_targeted = (
            "/chat/stream" in path
            or "/stream" in path
            or "/upload" in path
        )
        if not is_targeted:
            return await call_next(request)

        from app.security.rate_limiter import get_rate_limiter

        client_ip = request.headers.get(
            "X-Forwarded-For", request.client.host if request.client else "unknown"
        ).split(",")[0].strip()

        user_roles = request.headers.get("X-User-Roles")
        limiter = get_rate_limiter()
        is_allowed, limit, remaining, reset_secs = await limiter.check_rate_limit(
            identifier=client_ip, user_roles=user_roles
        )

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Quota {limit} RPM reached. Retry after {reset_secs}s."},
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_secs),
                    "Retry-After": str(reset_secs),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_secs)
        return response


def register_middlewares(app: FastAPI) -> None:
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(APIKeyAuthMiddleware)
