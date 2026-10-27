"""多数据源引擎: 连接构建、连接池缓存、元数据探测与只读查询执行。

移植 SQLBot `apps/db/db.py` 的多数据源能力:
- 按数据源类型构建 SQLAlchemy 连接 URL(Oracle service_name/SID、ClickHouse http/native 等)
- 连接池按数据源缓存, 配置变化时自动重建并释放旧连接
- 连接探测(版本 + 耗时)、schema 列表、线上表/字段读取、表数据预览
- 元数据同步优先使用各数据库的系统视图(能拿到表/字段注释), 失败时回退 inspector
"""
import asyncio
import base64
import hashlib
import logging
import threading
import time
import urllib.parse
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID as UUIDType

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.engines import dm, metadata_sql
from app.engines.dialects import (
    build_query_string,
    get_dialect,
    quote_identifier,
    split_extra_params,
)

logger = logging.getLogger(__name__)

# 连接池缓存: 数据源 ID -> (Engine, 指纹)。指纹变化(配置更新)时重建
_engine_cache: Dict[str, Tuple[Engine, str]] = {}
_cache_lock = threading.Lock()


# ========== 密码加密(Fernet, 密钥派生自 JWT_SECRET) ==========

def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_password(plain: str) -> bytes:
    return _fernet().encrypt((plain or "").encode())


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


def _password(ds) -> str:
    """探测配置直接携带明文密码; 已保存的数据源使用加密字段。"""
    plain = getattr(ds, "password", None)
    if plain:
        return str(plain)
    return decrypt_password(getattr(ds, "password_enc", None))


# ========== 连接 URL ==========

def build_url(ds) -> str:
    """根据数据源配置构建 SQLAlchemy 连接 URL。"""
    dialect = get_dialect(ds.db_type)
    if dialect.db_type == "dm":
        raise ValueError("达梦使用 dmPython 原生适配器，不构建 SQLAlchemy 连接 URL")
    host = (getattr(ds, "host", "") or "").strip() or "localhost"
    port = int(getattr(ds, "port", 0) or dialect.default_port)
    database = (getattr(ds, "database_name", "") or "").strip()
    username = (getattr(ds, "username", "") or "").strip()
    password = _password(ds)
    extra = split_extra_params(dialect.db_type, getattr(ds, "extra_jdbc", None))

    scheme = dialect.driver
    if dialect.db_type == "clickhouse":
        # 9000/9440 走原生协议, 其余走 HTTP(clickhouse-connect)
        if port in (9000, 9440):
            scheme = "clickhouse"
        elif port == 8443:
            scheme = "clickhouse+https"

    auth = ""
    if username:
        auth = f"{urllib.parse.quote_plus(username)}:{urllib.parse.quote_plus(password)}@"

    url = f"{scheme}://{auth}{host}:{port}"

    if dialect.db_type == "oracle":
        mode = (getattr(ds, "connect_mode", None) or "service_name").lower()
        if mode == "sid":
            url += f"/{urllib.parse.quote(database)}"
        else:
            url += f"/?service_name={urllib.parse.quote(database)}"
    elif database:
        url += f"/{urllib.parse.quote(database)}"

    query = build_query_string(extra)
    if query:
        url += ("&" if "?" in url else "?") + query
    return url


def _connect_args(ds) -> Dict[str, Any]:
    """按数据库类型构造驱动级连接参数。"""
    dialect = get_dialect(ds.db_type)
    timeout = int(getattr(ds, "timeout", 0) or 30)
    query_timeout = max(timeout, settings.query_timeout_sec)
    schema = (getattr(ds, "db_schema", None) or "").strip()
    args: Dict[str, Any] = {}

    if dialect.db_type == "postgresql":
        options = [f"-c statement_timeout={max(1000, settings.query_timeout_sec * 1000)}"]
        if schema:
            options.insert(0, f"-c search_path={schema}")
        args["connect_timeout"] = timeout
        args["options"] = " ".join(options)
    elif dialect.db_type == "kingbase":
        if schema:
            args["options"] = f"-c search_path={schema}"
        args["connect_timeout"] = timeout
    elif dialect.db_type == "redshift":
        # Redshift 对 libpq options 支持有限, 仅设置连接超时
        args["connect_timeout"] = timeout
    elif dialect.db_type in ("mysql", "doris", "starrocks"):
        args.update(connect_timeout=timeout, read_timeout=query_timeout,
                    write_timeout=query_timeout)
        if getattr(ds, "ssl", False):
            args["ssl"] = {"ssl_mode": "REQUIRE"}
    elif dialect.db_type == "clickhouse":
        args.update(connect_timeout=timeout, send_receive_timeout=query_timeout)
    elif dialect.db_type == "sqlserver":
        args.update(login_timeout=timeout, timeout=query_timeout)
        if getattr(ds, "low_version", False):
            # 低版本 SQL Server 使用 TDS 7.0 兼容模式(与 SQLBot 一致)
            args["tds_version"] = "7.0"
    elif dialect.db_type == "oracle":
        args["tcp_connect_timeout"] = timeout
    return args


def _cache_key(ds) -> str:
    return str(getattr(ds, "id", None) or "transient")


def _build_engine(ds, transient: bool = False) -> Engine:
    options: Dict[str, Any] = {
        "poolclass": NullPool,
    } if transient else {
        "pool_size": max(1, int(getattr(ds, "pool_size", 0) or 5)),
        "max_overflow": 10,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
        "pool_timeout": max(1, int(getattr(ds, "pool_timeout", 0) or 30)),
    }
    return create_engine(
        build_url(ds),
        connect_args=_connect_args(ds),
        future=True,
        **options,
    )


def get_engine(ds, cache: bool = True) -> Engine:
    """获取(或创建并缓存)数据源对应的连接池。

    cache=False 或数据源尚未入库(表单探测)时创建临时连接池, 不进入缓存。
    """
    key = _cache_key(ds)
    url = build_url(ds)
    fingerprint = f"{url}|{repr(sorted(_connect_args(ds).items()))}"

    if not cache or getattr(ds, "id", None) is None:
        return _build_engine(ds, transient=True)

    with _cache_lock:
        cached = _engine_cache.get(key)
        if cached and cached[1] == fingerprint:
            return cached[0]
        engine = _build_engine(ds)
        if cached:
            try:
                cached[0].dispose()
            except Exception:
                pass
        _engine_cache[key] = (engine, fingerprint)
        return engine


def dispose_engine(ds) -> None:
    """释放数据源连接池(删除/更新配置时调用)。"""
    key = str(getattr(ds, "id", None) or ds)
    try:
        dm.dispose_pool(ds)
    except Exception:
        logger.warning("释放达梦连接池失败: %s", key)
    with _cache_lock:
        cached = _engine_cache.pop(key, None)
    if cached:
        try:
            cached[0].dispose()
        except Exception:
            pass


# ========== 结果序列化 ==========

def _serialize_value(v: Any) -> Any:
    """将查询结果中的值转为 JSON 可序列化类型。"""
    if v is None or isinstance(v, (bool, int, str, float)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date, dtime)):
        return str(v)
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, UUIDType):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    if hasattr(v, "read"):  # Oracle LOB / 大对象
        try:
            data = v.read()
            return data.decode("utf-8", "ignore") if isinstance(data, bytes) else data
        except Exception:
            return str(v)
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


def _rows_to_dicts(result) -> List[Dict[str, Any]]:
    """把结果集转为小写列名的字典列表(兼容 Oracle 大写别名)。"""
    return [{str(k).lower(): v for k, v in row._mapping.items()} for row in result.fetchall()]


# ========== 核心执行 ==========

def _exec_raw(conn, sql: str):
    """执行原始 SQL。format/pyformat 风格驱动(psycopg2/pymysql/pymssql)会把 % 当作占位符,
    需转义为 %%, 否则 LIKE 'a%' 之类的语句会报错。"""
    if conn.dialect.paramstyle in ("format", "pyformat"):
        sql = sql.replace("%", "%%")
    return conn.exec_driver_sql(sql)


async def execute_query(datasource, sql: str) -> Tuple[List[Dict], List[Dict]]:
    """
    对指定数据源执行只读查询。
    返回 (data_rows, column_definitions):
      column_definitions: [{"name": "col", "type": "varchar"}, ...]
      data_rows: [{"col": value, ...}, ...]
    """
    max_rows = settings.max_query_rows

    def _run():
        if get_dialect(datasource.db_type).db_type == "dm":
            return dm.read_query(datasource, sql, max_rows + 1)
        engine = get_engine(datasource)
        with engine.connect() as conn:
            result = _exec_raw(conn, sql)
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


def _friendly_error(exc: Exception, label: str) -> str:
    msg = str(exc).strip().split("\n")[0][:300] or exc.__class__.__name__
    lowered = msg.lower()
    if "no module named" in lowered or "can't load plugin" in lowered:
        return f"{label} 驱动未安装或不可用: {msg}"
    if "timed out" in lowered or "timeout" in lowered:
        return f"连接超时: {msg}"
    if "access denied" in lowered or "authentication" in lowered or "password" in lowered:
        return f"认证失败, 请检查用户名/密码: {msg}"
    return msg


async def test_connection(datasource) -> Dict[str, Any]:
    """真实连接测试: 建立连接并读取数据库版本。"""
    dialect = get_dialect(datasource.db_type)
    started = time.time()
    wait_timeout = (max(1, int(getattr(datasource, "timeout", None) or 30)) + 5
                    if dialect.db_type == "dm" else 20)

    def _run() -> str:
        if dialect.db_type == "dm":
            return dm.test_connection(datasource)
        engine = get_engine(datasource, cache=False)
        try:
            with engine.connect() as conn:
                version = ""
                sql = metadata_sql.version_sql(dialect.db_type)
                if sql:
                    try:
                        row = conn.exec_driver_sql(sql).first()
                        version = str(row[0]) if row and row[0] is not None else ""
                    except Exception:
                        conn.exec_driver_sql("SELECT 1")
                else:
                    conn.exec_driver_sql("SELECT 1")
                return version
        finally:
            engine.dispose()

    try:
        version = await asyncio.wait_for(asyncio.to_thread(_run), timeout=wait_timeout)
    except asyncio.TimeoutError:
        raise ConnectionError(
            f"连接超时(>{wait_timeout}s), 请检查 {datasource.host}:{datasource.port} 是否可达"
        )
    except ImportError as e:
        raise ConnectionError(
            f"缺少 {dialect.label} 驱动, 请执行: pip install {dialect.driver_package} ({e})"
        )
    except Exception as e:
        raise ConnectionError(_friendly_error(e, dialect.label))

    return {
        "success": True,
        "message": f"{dialect.label} 连接成功",
        "version": (version or "").split("\n")[0][:120],
        "latency_ms": int((time.time() - started) * 1000),
        "server": f"{datasource.host}:{datasource.port}",
    }


# ========== 元数据探测 ==========

def _table_params(ds) -> Tuple[Optional[str], Optional[str]]:
    dialect = get_dialect(ds.db_type)
    schema = (getattr(ds, "db_schema", None) or "").strip() or (dialect.default_schema or None)
    if dialect.db_type == "oracle" and not schema:
        # Oracle 未显式指定 schema 时按当前用户(用户名大写)查询
        username = (getattr(ds, "username", None) or "").strip()
        schema = username.upper() or None
    database = (getattr(ds, "database_name", None) or "").strip() or (
        schema if dialect.supports_schema else None
    )
    return database, schema


def _fetch_tables(engine: Engine, ds) -> List[Dict[str, Any]]:
    """读取表清单, ClickHouse 低版本自动降级为无注释查询。"""
    database, schema = _table_params(ds)
    db_type = get_dialect(ds.db_type).db_type
    attempts = [False, True] if db_type == "clickhouse" else [False]
    last_error: Optional[Exception] = None
    for legacy in attempts:
        sql, params = metadata_sql.table_sql(db_type, database, schema, legacy=legacy)
        try:
            with engine.connect() as conn:
                rows = _rows_to_dicts(conn.execute(text(sql), params))
            return [
                {
                    "table_name": str(r.get("table_name") or ""),
                    "table_comment": str(r.get("table_comment") or ""),
                }
                for r in rows
                if r.get("table_name")
            ]
        except Exception as e:  # 系统视图差异/权限不足
            last_error = e
            continue
    raise RuntimeError(f"读取表清单失败: {last_error}")


def _fetch_columns(engine: Engine, ds, table_name: Optional[str]) -> List[Dict[str, Any]]:
    """读取字段清单(含注释/可空), 返回带 table_name 的扁平列表。"""
    database, schema = _table_params(ds)
    sql, params = metadata_sql.field_sql(
        get_dialect(ds.db_type).db_type, database, schema, table_name
    )
    with engine.connect() as conn:
        rows = _rows_to_dicts(conn.execute(text(sql), params))
    columns = []
    for r in rows:
        if not r.get("column_name"):
            continue
        nullable = str(r.get("is_nullable") or "YES").strip().upper()
        columns.append({
            "table_name": str(r.get("table_name") or table_name or ""),
            "column_name": str(r["column_name"]),
            "column_type": str(r.get("data_type") or ""),
            "column_comment": str(r.get("column_comment") or ""),
            "is_nullable": 0 if nullable in ("NO", "N", "FALSE", "0") else 1,
            "is_primary_key": 0,
            "default_value": None,
        })
    return columns


def _fetch_primary_keys(engine: Engine, ds, tables: List[str]) -> Dict[str, set]:
    """批量获取主键列(inspector 优先, 失败返回空)。"""
    if not tables:
        return {}
    dialect = get_dialect(ds.db_type)
    schema = None
    if dialect.supports_schema:
        schema = (getattr(ds, "db_schema", None) or dialect.default_schema or "").strip() or None
    try:
        insp = inspect(engine)
        result = insp.get_multi_pk_constraint(tables, schema=schema)
    except Exception:
        return {}
    pk_map: Dict[str, set] = {}
    for table, info in (result or {}).items():
        columns = (info or {}).get("constrained_columns") or []
        pk_map[str(table).lower()] = {str(c).lower() for c in columns}
    return pk_map


def _sync_via_inspector(engine: Engine, ds, only_tables: Optional[List[str]]) -> List[Dict]:
    """系统视图不可用时的兜底: 使用 SQLAlchemy inspector 内省。"""
    dialect = get_dialect(ds.db_type)
    schema = None
    if dialect.supports_schema:
        schema = (getattr(ds, "db_schema", None) or dialect.default_schema or "").strip() or None
    insp = inspect(engine)
    names = insp.get_table_names(schema=schema)
    if only_tables:
        wanted = {t.lower() for t in only_tables}
        names = [n for n in names if n.lower() in wanted]
    tables_info = []
    for name in names:
        columns = []
        try:
            comment = (insp.get_table_comment(name, schema=schema) or {}).get("text")
        except Exception:
            comment = None
        for c in insp.get_columns(name, schema=schema):
            columns.append({
                "column_name": c["name"],
                "column_type": str(c["type"]),
                "column_comment": c.get("comment") or "",
                "is_nullable": 0 if c.get("nullable", True) is False else 1,
                "is_primary_key": 1 if c.get("pk") else 0,
                "default_value": str(c["default"]) if c.get("default") is not None else None,
            })
        tables_info.append({
            "table_name": name,
            "table_comment": comment or "",
            "columns": columns,
        })
    return tables_info


def _sync_schema_sync(ds, only_tables: Optional[List[str]] = None) -> List[Dict]:
    """同步表结构: 一次读取全部字段, 批量补主键, 按表聚合。"""
    if get_dialect(ds.db_type).db_type == "dm":
        return dm.sync_schema(ds, only_tables)
    engine = get_engine(ds)
    try:
        table_rows = _fetch_tables(engine, ds)
        if only_tables:
            wanted = {t.lower() for t in only_tables}
            table_rows = [t for t in table_rows if t["table_name"].lower() in wanted]
        if not table_rows:
            return []

        try:
            columns = _fetch_columns(engine, ds, None)
        except Exception:
            return _sync_via_inspector(engine, ds, only_tables)

        grouped: Dict[str, List[Dict]] = {}
        for col in columns:
            grouped.setdefault(col["table_name"].lower(), []).append(col)

        pk_map = _fetch_primary_keys(engine, ds, [t["table_name"] for t in table_rows])

        tables_info = []
        for t in table_rows:
            cols = grouped.get(t["table_name"].lower(), [])
            pks = pk_map.get(t["table_name"].lower(), set())
            for col in cols:
                col["is_primary_key"] = 1 if col["column_name"].lower() in pks else 0
                # 落库时按表分组, 列级别不需要重复表名
                col.pop("table_name", None)
            tables_info.append({
                "table_name": t["table_name"],
                "table_comment": t["table_comment"],
                "columns": cols,
            })
        return tables_info
    except Exception as e:
        logger.warning("元数据同步失败, 回退 inspector: %s", e)
        return _sync_via_inspector(engine, ds, only_tables)


async def sync_schema(datasource, only_tables: Optional[List[str]] = None) -> List[Dict]:
    """
    从数据源数据库自动内省表结构(可指定表)。
    返回: [{"table_name": "t", "table_comment": ..., "columns": [{...}]}]
    """
    return await asyncio.wait_for(
        asyncio.to_thread(_sync_schema_sync, datasource, only_tables), timeout=120
    )


async def list_schemas(datasource) -> List[str]:
    """列出可选的 schema/库名, 供前端下拉。"""
    def _run() -> List[str]:
        if get_dialect(datasource.db_type).db_type == "dm":
            return dm.list_schemas(datasource)
        sql = metadata_sql.schema_sql(get_dialect(datasource.db_type).db_type)
        if not sql:
            return []
        engine = get_engine(datasource)
        with engine.connect() as conn:
            rows = _exec_raw(conn, sql).fetchall()
        return sorted({str(r[0]) for r in rows if r[0] is not None})

    return await asyncio.wait_for(asyncio.to_thread(_run), timeout=30)


async def list_tables(datasource) -> List[Dict[str, Any]]:
    """实时读取数据源中的表清单(不落库)。"""
    def _run():
        if get_dialect(datasource.db_type).db_type == "dm":
            return dm.list_tables(datasource)
        engine = get_engine(datasource)
        return _fetch_tables(engine, datasource)

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=60)
    except asyncio.TimeoutError:
        raise TimeoutError("读取表清单超时(>60s)")
    except Exception as e:
        raise RuntimeError(_friendly_error(e, get_dialect(datasource.db_type).label))


async def list_columns(datasource, table_name: str) -> List[Dict[str, Any]]:
    """实时读取单表字段清单(不落库)。"""
    def _run():
        if get_dialect(datasource.db_type).db_type == "dm":
            return dm.list_columns(datasource, table_name)
        engine = get_engine(datasource)
        return _fetch_columns(engine, datasource, table_name)

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=60)
    except asyncio.TimeoutError:
        raise TimeoutError("读取字段清单超时(>60s)")
    except Exception as e:
        raise RuntimeError(_friendly_error(e, get_dialect(datasource.db_type).label))


def qualified_table_name(datasource, table_name: str) -> str:
    """按方言拼装带 schema 的限定表名。"""
    dialect = get_dialect(datasource.db_type)
    name = quote_identifier(dialect.db_type, table_name)
    schema = (getattr(datasource, "db_schema", None) or "").strip()
    if dialect.db_type == "dm" and not schema:
        raise ValueError("达梦数据源必须指定 Schema / 模式")
    if dialect.supports_schema and schema:
        return f"{quote_identifier(dialect.db_type, schema)}.{name}"
    return name


async def preview_table(datasource, table_name: str, limit: int = 50) -> Dict[str, Any]:
    """预览表数据(最多 limit 行), 用 fetchmany 规避各数据库 LIMIT 语法差异。"""
    max_rows = max(1, min(int(limit or 50), 200))

    def _run():
        sql = f"SELECT * FROM {qualified_table_name(datasource, table_name)}"
        if get_dialect(datasource.db_type).db_type == "dm":
            return dm.read_query(datasource, f"{sql} LIMIT {max_rows}", max_rows)
        engine = get_engine(datasource)
        with engine.connect() as conn:
            result = _exec_raw(conn, sql)
            keys = list(result.keys())
            rows = result.fetchmany(max_rows)
            return keys, rows

    try:
        keys, rows = await asyncio.wait_for(asyncio.to_thread(_run), timeout=60)
    except asyncio.TimeoutError:
        raise TimeoutError("预览数据超时(>60s)")
    except Exception as e:
        raise RuntimeError(_friendly_error(e, get_dialect(datasource.db_type).label))

    data = [{k: _serialize_value(row[i]) for i, k in enumerate(keys)} for row in rows]
    columns = [{"name": k, "type": _derive_type(data[0].get(k)) if data else "text"} for k in keys]
    return {"table_name": table_name, "columns": columns, "data": data, "row_count": len(data)}
