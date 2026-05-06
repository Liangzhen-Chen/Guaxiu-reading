"""
朽瓜（Xiugua）FastAPI 应用入口。
启动：uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.database import init_db
from app.routers import routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时执行"""
    await init_db()
    yield


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

# CORS —— 仅允许指定前端域名和本地开发
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

# 安全响应头
app.add_middleware(SecurityHeadersMiddleware)


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

# 注册所有路由
for router in routers:
    app.include_router(router)

# 头像静态文件
import os
avatar_path = os.path.join(os.path.dirname(settings.book_storage_path), "avatars")
os.makedirs(avatar_path, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=avatar_path), name="avatars")
