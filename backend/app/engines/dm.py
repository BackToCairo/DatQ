"""达梦原生适配器：沿用 SQLBot 的 dmPython 与系统视图，不依赖 SQLAlchemy 方言插件。"""
import hashlib
import importlib
import json
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from sqlalchemy.pool import NullPool, Pool, QueuePool

from app.config import settings
from app.engines import metadata_sql
from app.engines.dialects import quote_identifier, split_extra_params

_pool_cache: Dict[str, tuple] = {}
_pool_lock = threading.Lock()
_RESERVED_PARAMS = {
    "user", "username", "password", "server", "host", "port", "dsn",
    "database", "database_name", "schema", "connection_timeout", "autocommit",
}


def _load_driver():
    """惰性加载；不使用达梦时不影响其他数据源或应用启动。"""
    try:
        return importlib.import_module("dmPython")
    except (ImportError, OSError) as exc:
        raise ImportError("dmPython 或达梦原生运行库不可用，请安装 dmPython==2.5.22") from exc


def _schema(ds, required: bool = True) -> str:
    schema = (getattr(ds, "db_schema", None) or "").strip()
    if required and not schema:
        raise ValueError("达梦数据源必须指定 Schema / 模式")
    return schema


def _snapshot(ds):
    # 缓存的 creator 只捕获配置快照，不能保留生命周期更短的 ORM 对象。
    from app.engines import _password

    extra = split_extra_params("dm", getattr(ds, "extra_jdbc", None))
    if any(key.lower() in _RESERVED_PARAMS for key in extra):
        raise ValueError("达梦附加参数不能覆盖账号、地址、Schema、超时或事务设置")
    converted = {}
    for key, value in extra.items():
        if value.lstrip("-").isdigit():
            converted[key] = int(value)
        elif value.lower() in ("true", "false"):
            converted[key] = value.lower() == "true"
        else:
            converted[key] = value
    config = {
        "user": (getattr(ds, "username", None) or "").strip(),
        "password": _password(ds),
        "server": (getattr(ds, "host", None) or "localhost").strip(),
        "port": int(getattr(ds, "port", None) or 5236),
        "connection_timeout": max(1, int(getattr(ds, "timeout", None) or 30)),
        **converted,
    }
    pool_size = max(1, int(getattr(ds, "pool_size", None) or 5))
    pool_timeout = max(1, int(getattr(ds, "pool_timeout", None) or 30))
    fingerprint = hashlib.sha256(json.dumps(
        [config, _schema(ds, required=False), pool_size, pool_timeout],
        sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()
    return config, pool_size, pool_timeout, fingerprint


def get_pool(ds, cache: bool = True) -> Pool:
    config, size, timeout, fingerprint = _snapshot(ds)
    creator = lambda: _load_driver().connect(**config)
    ds_id = getattr(ds, "id", None)
    if not cache or ds_id is None:
        return NullPool(creator, reset_on_return="rollback")
    key = str(ds_id)
    with _pool_lock:
        previous = _pool_cache.get(key)
        if previous and previous[1] == fingerprint:
            return previous[0]
        pool = QueuePool(creator, pool_size=size, max_overflow=10, timeout=timeout,
                         recycle=1800, reset_on_return="rollback")
        if previous:
            previous[0].dispose()
        _pool_cache[key] = (pool, fingerprint)
        return pool


def dispose_pool(ds) -> None:
    key = str(getattr(ds, "id", None) or ds)
    with _pool_lock:
        previous = _pool_cache.pop(key, None)
    if previous:
        previous[0].dispose()


@contextmanager
def _cursor(conn):
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _execute(cursor, sql: str, params: Optional[Dict] = None, timeout: int = 30):
    # dmPython 支持 SQLBot 使用的命名参数字典；不套用 format 驱动的百分号转义。
    if params:
        cursor.execute(sql, params, timeout=timeout)
    else:
        cursor.execute(sql, timeout=timeout)


@contextmanager
def connection(ds, cache: bool = True):
    pool = get_pool(ds, cache=cache)
    transient = not cache or getattr(ds, "id", None) is None
    conn = None
    timeout = max(1, int(getattr(ds, "timeout", None) or 30))
    try:
        conn = pool.connect()
        if not transient:
            # 原生 Pool 没有 SQLAlchemy 方言的 pre_ping，显式探活并重建失效连接。
            try:
                with _cursor(conn) as cursor:
                    _execute(cursor, "SELECT 1 FROM DUAL", timeout=timeout)
            except Exception as exc:
                conn.invalidate(exc)
                conn.close()
                conn = pool.connect()
        schema = _schema(ds, required=False)
        if schema:
            with _cursor(conn) as cursor:
                _execute(cursor, f"SET SCHEMA {quote_identifier('dm', schema)}", timeout=timeout)
        yield conn
    except Exception as exc:
        if conn is not None:
            # 执行失败的连接不放回池中，避免未结束事务或失效会话被再次使用。
            conn.invalidate(exc)
        raise
    finally:
        if conn is not None:
            conn.close()
        if transient:
            pool.dispose()


def read_query(ds, sql: str, max_rows: int):
    """返回列名和结果行；大对象必须在连接关闭前转为可序列化值。"""
    from app.engines import _serialize_value

    with connection(ds) as conn, _cursor(conn) as cursor:
        _execute(cursor, sql, timeout=max(1, settings.query_timeout_sec))
        keys = [str(col[0]) for col in (cursor.description or [])]
        rows = [tuple(_serialize_value(value) for value in row)
                for row in cursor.fetchmany(max_rows)]
    return keys, rows


def test_connection(ds) -> str:
    with connection(ds, cache=False) as conn, _cursor(conn) as cursor:
        timeout = max(1, int(getattr(ds, "timeout", None) or 30))
        try:
            _execute(cursor, metadata_sql.version_sql("dm"), timeout=timeout)
            row = cursor.fetchone()
            return str(row[0]) if row and row[0] is not None else ""
        except Exception:
            _execute(cursor, "SELECT 1 FROM DUAL", timeout=timeout)
            return ""


def list_schemas(ds) -> List[str]:
    with connection(ds) as conn, _cursor(conn) as cursor:
        _execute(cursor, metadata_sql.schema_sql("dm"),
                 timeout=max(1, int(getattr(ds, "timeout", None) or 30)))
        return sorted({str(row[0]) for row in cursor.fetchall() if row[0] is not None})


def _metadata_rows(conn, sql: str, params: Dict, timeout: int) -> List[Dict[str, Any]]:
    from app.engines import _serialize_value

    with _cursor(conn) as cursor:
        _execute(cursor, sql, params, timeout=timeout)
        keys = [str(col[0]).lower() for col in (cursor.description or [])]
        return [dict(zip(keys, (_serialize_value(value) for value in row)))
                for row in cursor.fetchall()]


def _tables(conn, ds) -> List[Dict[str, Any]]:
    sql, params = metadata_sql.table_sql("dm", None, _schema(ds))
    rows = _metadata_rows(conn, sql, params, max(1, settings.query_timeout_sec))
    return [{"table_name": str(row["table_name"]),
             "table_comment": str(row.get("table_comment") or "")}
            for row in rows if row.get("table_name")]


def _columns(conn, ds, table_name: Optional[str]) -> List[Dict[str, Any]]:
    sql, params = metadata_sql.field_sql("dm", None, _schema(ds), table_name)
    rows = _metadata_rows(conn, sql, params, max(1, settings.query_timeout_sec))
    columns = []
    for row in rows:
        if not row.get("column_name"):
            continue
        nullable = str(row.get("is_nullable") or "YES").strip().upper()
        default = row.get("default_value")
        columns.append({
            "table_name": str(row.get("table_name") or table_name or ""),
            "column_name": str(row["column_name"]),
            "column_type": str(row.get("data_type") or ""),
            "column_comment": str(row.get("column_comment") or ""),
            "is_nullable": 0 if nullable in ("NO", "N", "FALSE", "0") else 1,
            "is_primary_key": 1 if str(row.get("is_primary_key")) == "1" else 0,
            "default_value": str(default) if default is not None else None,
        })
    return columns


def list_tables(ds) -> List[Dict[str, Any]]:
    _schema(ds)
    with connection(ds) as conn:
        return _tables(conn, ds)


def list_columns(ds, table_name: str) -> List[Dict[str, Any]]:
    _schema(ds)
    with connection(ds) as conn:
        return _columns(conn, ds, table_name)


def sync_schema(ds, only_tables: Optional[List[str]] = None) -> List[Dict]:
    """保留大小写精确分组，避免引号创建的同名不同大小写对象互相污染。"""
    _schema(ds)
    with connection(ds) as conn:
        tables = _tables(conn, ds)
        if only_tables:
            wanted = set(only_tables)
            tables = [table for table in tables if table["table_name"] in wanted]
        if not tables:
            return []
        grouped: Dict[str, List[Dict]] = {}
        for column in _columns(conn, ds, None):
            name = column.pop("table_name")
            grouped.setdefault(name, []).append(column)
        return [{**table, "columns": grouped.get(table["table_name"], [])} for table in tables]
