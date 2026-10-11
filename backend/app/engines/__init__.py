"""Database engine utilities: connection pools, query execution, schema sync.

支持多数据源类型(postgresql/mysql/clickhouse),使用 SQLAlchemy 同步引擎 +
asyncio.to_thread 执行,按数据源缓存连接池,密码使用 Fernet 加密存储。
"""
import hashlib
import base64
import logging
from typing import List, Dict, Tuple, Any
from datetime import datetime, date, time as dtime
from decimal import Decimal
from uuid import UUID as UUIDType

import asyncio
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)

# 连接池缓存: key -> (Engine, url)。url 变化(配置更新)时自动重建
_engine_cache: Dict[Any, Tuple[Engine, str]] = {}

_DIALECT_MAP = {
    "postgresql": "postgresql+psycopg2",
    "mysql": "mysql+pymysql",
    "clickhouse": "clickhouse",  # clickhouse-sqlalchemy 原生协议(默认9000端口)
}


# ========== 密码加密(Fernet, 密钥派生自 JWT_SECRET) ==========

def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_password(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode())


def decrypt_password(stored: bytes) -> str:
    """兼容历史明文存储: 解密失败时按明文处理。"""
    if stored is None:
        return ""
    try:
        return _fernet().decrypt(bytes(stored)).decode()
    except (InvalidToken, Exception):
        try:
            return bytes(stored).decode()
        except Exception:
            return ""


# ========== 连接管理 ==========

def build_url(ds) -> str:
    """根据数据源配置构建 SQLAlchemy 连接 URL。"""
    scheme = _DIALECT_MAP.get(ds.db_type)
    if not scheme:
        raise ValueError(f"不支持的数据源类型: {ds.db_type}")
    password = decrypt_password(ds.password_enc).replace("@", "%40")
    return f"{scheme}://{ds.username}:{password}@{ds.host}:{ds.port}/{ds.database_name}"


def _cache_key(ds) -> Any:
    return str(ds.id) if hasattr(ds, "id") else str(ds)


def get_engine(ds) -> Engine:
    """获取(或创建并缓存)数据源对应的连接池。"""
    url = build_url(ds)
    key = _cache_key(ds)
    cached = _engine_cache.get(key)
    if cached and cached[1] == url:
        return cached[0]

    connect_args = {}
    if ds.db_type == "postgresql":
        # 语句级超时(毫秒)
        timeout_ms = max(1000, settings.query_timeout_sec * 1000)
        connect_args = {"options": f"-c statement_timeout={timeout_ms}", "connect_timeout": 10}
    elif ds.db_type == "mysql":
        connect_args = {"connect_timeout": 10, "read_timeout": settings.query_timeout_sec}

    engine = create_engine(
        url,
        pool_size=ds.pool_size or 5,
        pool_timeout=ds.pool_timeout or 30,
        pool_recycle=1800,
        max_overflow=5,
        connect_args=connect_args,
    )
    if cached:
        try:
            cached[0].dispose()
        except Exception:
            pass
    _engine_cache[key] = (engine, url)
    return engine


def dispose_engine(ds) -> None:
    cached = _engine_cache.pop(_cache_key(ds), None)
    if cached:
        try:
            cached[0].dispose()
        except Exception:
            pass


def _serialize_value(v: Any) -> Any:
    """将查询结果中的值转为 JSON 可序列化类型。"""
    if v is None or isinstance(v, (bool, int, str, float)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date, dtime)):
        return str(v)
    if isinstance(v, UUIDType):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    return str(v)


def _derive_type(value: Any) -> str:
    if value is None:
        return "text"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (datetime, date, dtime)):
        return "datetime"
    return "varchar"


# ========== 核心执行 ==========

async def execute_query(datasource, sql: str) -> Tuple[List[Dict], List[Dict]]:
    """
    对指定数据源执行只读查询。
    返回 (data_rows, column_definitions):
      column_definitions: [{"name": "col", "type": "varchar"}, ...]
      data_rows: [{"col": value, ...}, ...]
    """
    max_rows = settings.max_query_rows
    engine = get_engine(datasource)

    def _run():
        with engine.connect() as conn:
            result = conn.exec_driver_sql(sql)
            keys = list(result.keys())
            rows = result.fetchmany(max_rows + 1)
            return keys, rows

    try:
        keys, rows = await asyncio.wait_for(
            asyncio.to_thread(_run), timeout=settings.query_timeout_sec + 5
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"查询超时(>{settings.query_timeout_sec}s)")
    except Exception as e:
        msg = str(e).split("\n")[0][:500]
        raise RuntimeError(msg)

    if len(rows) > max_rows:
        raise RuntimeError(f"查询结果超过最大行数限制({max_rows}行),请缩小查询范围")

    columns = [{"name": k, "type": "text"} for k in keys]
    data = []
    for row in rows:
        item = {}
        for i, k in enumerate(keys):
            val = _serialize_value(row[i])
            item[k] = val
            if columns[i]["type"] == "text" and val is not None:
                columns[i]["type"] = _derive_type(val)
        data.append(item)
    return data, columns


async def test_connection(datasource) -> Dict[str, Any]:
    """真实连接测试: 建立连接并执行 SELECT 1。"""
    engine = get_engine(datasource)

    def _run():
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
            return engine.pool.status()

    try:
        await asyncio.wait_for(asyncio.to_thread(_run), timeout=15)
        return {"status": "success", "message": "连接成功"}
    except Exception as e:
        msg = str(e).split("\n")[0][:300]
        raise ConnectionError(msg)


# ========== Schema 同步 ==========

def _sync_schema_sync(ds) -> List[Dict]:
    """通过 SQLAlchemy inspector 内省表结构(同步上下文中执行)。"""
    engine = get_engine(ds)
    insp = inspect(engine)
    tables_info = []
    for tname in insp.get_table_names():
        if tname.startswith("pg_") or tname.startswith("sqlite_"):
            continue
        comment = None
        try:
            comment = insp.get_table_comment(tname).get("text")
        except Exception:
            pass  # 部分方言不支持表注释
        columns = []
        for c in insp.get_columns(tname):
            columns.append({
                "column_name": c["name"],
                "column_type": str(c["type"]),
                "column_comment": c.get("comment"),
                "is_nullable": 0 if c.get("nullable", True) is False else 1,
                "is_primary_key": 1 if c.get("pk") else 0,
                "default_value": str(c["default"]) if c.get("default") is not None else None,
            })
        tables_info.append({
            "table_name": tname,
            "table_comment": comment,
            "columns": columns,
        })
    return tables_info


async def sync_schema(datasource) -> List[Dict]:
    """
    从数据源数据库自动内省表结构。
    返回: [{"table_name": "t", "table_comment": ..., "columns": [{...}]}]
    """
    return await asyncio.wait_for(
        asyncio.to_thread(_sync_schema_sync, datasource), timeout=60
    )
