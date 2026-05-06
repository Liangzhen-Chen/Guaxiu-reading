"""
朽瓜（Xiugua）FastAPI 应用入口。
启动：uvicorn app.main:app --reload
"""
import logging
import os
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db
from app.log_utils import (
    error_log,
    generate_request_id,
    get_request_id,
    request_id_ctx,
    setup_logging,
)
from app.middleware.auth import get_current_user
from app.routers import routers

# ── Configure structured JSON logging ──
setup_logging()
logger = logging.getLogger(__name__)

# ── Server start time (for uptime calculation) ──
_app_start_time: float = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时执行"""
    global _app_start_time
    _app_start_time = time.time()
    await init_db()
    logger.info(
        "application_started",
        extra={
            "event": "startup",
            "app": settings.app_name,
            "version": settings.app_version,
        },
    )
    yield
    logger.info(
        "application_stopped",
        extra={"event": "shutdown"},
    )


# ── Middleware stack (first-added = outermost) ──


class RequestIDLoggingMiddleware(BaseHTTPMiddleware):
    """Generates a unique request ID per request, logs structured JSON, and
    records 5xx responses into the global error ring-buffer.

    Request ID is injected into the response as ``X-Request-ID`` and made
    available to downstream code via ``get_request_id()``.
    """

    async def dispatch(self, request, call_next):
        rid = generate_request_id()
        token = request_id_ctx.set(rid)
        start = time.perf_counter()

        # Try to extract user_id from JWT (best-effort; many routes are public)
        user_id = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from app.services.auth_service import decode_token
                user_id = decode_token(auth_header[7:])
            except Exception:
                pass

        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Build structured log entry
        log_extra = {
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
        if user_id:
            log_extra["user_id"] = str(user_id)

        logger.info("request", extra=log_extra)

        # Track server errors in ring-buffer for /debug/status
        if response.status_code >= 500:
            error_log.append((time.time(), request.method, request.url.path, response.status_code))

        response.headers["X-Request-ID"] = rid
        request_id_ctx.reset(token)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全响应头（HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy）"""

    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# 1. Request ID + logging (outermost — captures everything)
app.add_middleware(RequestIDLoggingMiddleware)

# 2. CORS —— 仅允许指定前端域名和本地开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.xiugua-reading.cn",
        "https://xiugua-reading.cn",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 安全响应头 (innermost)
app.add_middleware(SecurityHeadersMiddleware)


# ── Public endpoints ──


@app.get("/")
async def root():
    return {"app": settings.app_name, "version": settings.app_version}


@app.get("/health")
async def health():
    from app.database import async_session
    from sqlalchemy import text

    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        return {"status": "degraded", "database": "down"}


# ── Private debug endpoint ──


@app.get("/debug/status")
async def debug_status(user=Depends(get_current_user)):
    """Auth-protected status dashboard returning system health data."""
    from app.database import async_session
    from sqlalchemy import text

    # 1. Database connectivity
    db_ok = False
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    # 2. Last 10 server errors
    recent_errors = []
    for ts, method, path, sc in list(error_log)[-10:]:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        recent_errors.append({"timestamp": dt, "method": method, "path": path, "status_code": sc})

    # 3. Uptime
    uptime_seconds = time.time() - _app_start_time

    # 4. Systemd service status
    service_status = "unknown"
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "xiugua.service"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        service_status = result.stdout.strip()
    except Exception:
        service_status = "unreachable"

    # 5. Disk usage
    disk = shutil.disk_usage("/")
    disk_usage_pct = round(disk.used / disk.total * 100, 1)

    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "database": {"connected": db_ok},
        "uptime_seconds": int(uptime_seconds),
        "uptime_human": _format_uptime(uptime_seconds),
        "last_10_errors": recent_errors,
        "error_count_24h": _count_recent_errors(86400),
        "service": {"name": "xiugua", "status": service_status},
        "disk": {"usage_pct": disk_usage_pct, "total_gb": round(disk.total / 1e9, 1)},
        "request_id": get_request_id(),
    }


def _format_uptime(seconds: float) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _count_recent_errors(window_seconds: float) -> int:
    now = time.time()
    return sum(1 for entry in error_log if now - entry[0] < window_seconds)


# ── Mount routers ──
for router in routers:
    app.include_router(router)

# ── 头像静态文件 ──
avatar_path = os.path.join(os.path.dirname(settings.book_storage_path), "avatars")
os.makedirs(avatar_path, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=avatar_path), name="avatars")
