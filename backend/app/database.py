"""Database connection and session management."""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    hide_parameters=True,  # SQL 日志和异常不输出配置密文或其他绑定参数
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db():
    """Dependency: get async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# create_all 只建表不补列, 多数据源改造新增的字段在此幂等补齐(PostgreSQL 语法)
_SCHEMA_PATCHES = (
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS db_schema VARCHAR(128)",
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS connect_mode VARCHAR(32) DEFAULT 'service_name'",
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS ssl BOOLEAN DEFAULT FALSE",
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS extra_jdbc TEXT",
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS low_version BOOLEAN DEFAULT FALSE",
    "ALTER TABLE datasources ADD COLUMN IF NOT EXISTS timeout INTEGER DEFAULT 30",
)


async def init_db():
    """Initialize database tables (for development only)."""
    async with engine.begin() as conn:
        # 多 worker 串行检查及建表；锁随事务结束自动释放。
        await conn.execute(text("SELECT pg_advisory_xact_lock(681947200)"))
        await conn.run_sync(Base.metadata.create_all)
        for patch in _SCHEMA_PATCHES:
            try:
                # 每条补丁独立 SAVEPOINT, 失败只回滚自身, 不会让整个事务进入 aborted 状态
                async with conn.begin_nested():
                    await conn.execute(text(patch))
            except Exception as e:  # 旧版本数据库/权限不足时不阻断启动
                logger.warning("数据源表结构补列跳过: %s (%s)", patch, e)


async def close_db():
    """Close database engine."""
    await engine.dispose()
