"""
朽瓜（Xiugua）FastAPI 应用入口。
启动：uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时执行"""
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS —— 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"app": settings.app_name, "version": settings.app_version}


@app.get("/health")
async def health():
    return {"status": "ok"}

# 注册所有路由
for router in routers:
    app.include_router(router)
