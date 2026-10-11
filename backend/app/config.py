"""Application configuration management."""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "智能问数平台"
    app_env: str = "development"
    log_level: str = "INFO"
    debug: bool = True

    # Database
    db_user: str = "smart_query"
    db_password: str = "smart_query_2026"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "smart_query"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_sync(self) -> str:
        return f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = "redis_2026"

    @property
    def redis_url(self) -> str:
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"

    # ChromaDB
    chromadb_host: str = "localhost"
    chromadb_port: int = 8001

    # JWT
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    jwt_refresh_expire_days: int = 7

    # LLM
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_base_url: Optional[str] = None
    llm_embedding_enabled: bool = True  # 供应商无 embeddings 端点时(如 DeepSeek)置 false
    embedding_model: str = "text-embedding-3-small"

    # Application limits
    max_query_rows: int = 1000
    query_timeout_sec: int = 30
    rate_limit_qpm: int = 20

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
