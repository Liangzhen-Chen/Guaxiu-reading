"""
PostgreSQL 数据库连接。
使用 SQLAlchemy 异步引擎 + asyncpg 驱动。
⚠️ 预留切换口：修改 DATABASE_URL 即可切到 RDS / Supabase
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：每次请求获取一个数据库会话"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """创建所有表（首次启动时调用）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
