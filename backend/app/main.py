"""Smart Query Platform - FastAPI Application Entry Point."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db, close_db
from app.api.v1 import api_v1_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    await init_db()
    # 开发环境幂等种子: 默认角色/权限/演示数据源/示例知识
    if settings.app_env == "development":
        try:
            from app.seed import run_seed
            await run_seed()
        except Exception as e:
            logger.warning("种子数据初始化跳过: %s", e)
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title=settings.app_name,
    description="企业级智能问数平台 - 自然语言查询数据分析",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routes
app.include_router(api_v1_router)


@app.get("/")
async def root():
    return {"message": "智能问数平台 API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
