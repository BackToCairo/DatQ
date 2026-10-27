"""各数据库的元数据查询 SQL(移植自 SQLBot `apps/db/db_sql.py`)。

统一返回列别名: TABLE_NAME / COLUMN_NAME / DATA_TYPE / COLUMN_COMMENT / IS_NULLABLE,
引擎层按小写键读取,因此大小写不敏感(Oracle 会自动大写)。
参数使用 SQLAlchemy 命名绑定(:param/:param1/:param2)。
"""
from typing import Dict, Optional, Tuple

from app.engines.dialects import normalize_db_type

TableSql = Tuple[str, Dict[str, str]]
FieldSql = Tuple[str, Dict[str, Optional[str]]]


def version_sql(db_type: Optional[str]) -> str:
    """查询数据库版本, 空字符串表示该类型不做版本探测。"""
    key = normalize_db_type(db_type)
    return {
        "mysql": "SELECT VERSION()",
        "doris": "SELECT VERSION()",
        "starrocks": "SELECT VERSION()",
        "postgresql": "SELECT version()",
        "redshift": "SELECT version()",
        "kingbase": "SELECT version()",
        "clickhouse": "SELECT version()",
        "sqlserver": "SELECT @@VERSION",
        "oracle": "SELECT version FROM v$instance",
        "dm": "SELECT * FROM v$version",
    }.get(key, "")


def schema_sql(db_type: Optional[str]) -> str:
    """列出可选的 schema/库名。"""
    key = normalize_db_type(db_type)
    return {
        "mysql": "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME",
        "doris": "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME",
        "starrocks": "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME",
        "postgresql": (
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' ORDER BY nspname"
        ),
        "redshift": (
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' ORDER BY nspname"
        ),
        "kingbase": (
            "SELECT nspname FROM pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema' ORDER BY nspname"
        ),
        "sqlserver": "SELECT name FROM sys.schemas ORDER BY name",
        "oracle": "SELECT username FROM all_users ORDER BY username",
        "clickhouse": "SELECT name FROM system.databases ORDER BY name",
        "dm": "SELECT OBJECT_NAME FROM all_objects WHERE object_type = 'SCH' ORDER BY OBJECT_NAME",
    }.get(key, "")


def table_sql(
    db_type: Optional[str],
    database: Optional[str],
    schema: Optional[str],
    legacy: bool = False,
) -> TableSql:
    """表清单查询。legacy=True 时使用不含注释列的兼容写法(低版本 ClickHouse)。"""
    key = normalize_db_type(db_type)
    if key == "mysql":
        return (
            """
            SELECT TABLE_NAME, COALESCE(TABLE_COMMENT, '') AS TABLE_COMMENT
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :param
              AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            ORDER BY TABLE_NAME
            """,
            {"param": database or ""},
        )
    if key in ("doris", "starrocks"):
        # Doris/StarRocks 的 TABLE_TYPE 取值不完全一致, 不做过滤
        return (
            """
            SELECT TABLE_NAME, COALESCE(TABLE_COMMENT, '') AS TABLE_COMMENT
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :param
            ORDER BY TABLE_NAME
            """,
            {"param": database or ""},
        )
    if key == "postgresql":
        return (
            """
            SELECT c.relname AS TABLE_NAME,
                   COALESCE(COALESCE(d.description, obj_description(c.oid)), '') AS TABLE_COMMENT
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
            WHERE n.nspname = :param
              AND c.relkind IN ('r', 'v', 'p', 'm')
              AND c.relname NOT LIKE 'pg_%'
              AND c.relname NOT LIKE 'sql_%'
            ORDER BY c.relname
            """,
            {"param": schema or "public"},
        )
    if key == "kingbase":
        return (
            """
            SELECT c.relname AS TABLE_NAME,
                   COALESCE(COALESCE(d.description, obj_description(c.oid)), '') AS TABLE_COMMENT
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
            WHERE n.nspname = :param
              AND c.relkind IN ('r', 'v', 'p', 'm')
            ORDER BY c.relname
            """,
            {"param": schema or "public"},
        )
    if key == "redshift":
        return (
            """
            SELECT relname AS TABLE_NAME,
                   COALESCE(obj_description(relfilenode::regclass, 'pg_class'), '') AS TABLE_COMMENT
            FROM pg_class
            WHERE relkind IN ('r', 'p', 'f')
              AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = :param)
            ORDER BY relname
            """,
            {"param": schema or "public"},
        )
    if key == "sqlserver":
        return (
            """
            SELECT t.TABLE_NAME AS TABLE_NAME,
                   COALESCE(ep.value, '') AS TABLE_COMMENT
            FROM INFORMATION_SCHEMA.TABLES t
            LEFT JOIN sys.extended_properties ep
                   ON ep.major_id = OBJECT_ID(t.TABLE_SCHEMA + '.' + t.TABLE_NAME)
                  AND ep.minor_id = 0
                  AND ep.name = 'MS_Description'
            WHERE t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
              AND t.TABLE_SCHEMA = :param
            ORDER BY t.TABLE_NAME
            """,
            {"param": schema or "dbo"},
        )
    if key == "oracle":
        return (
            """
            SELECT DISTINCT t.TABLE_NAME AS TABLE_NAME,
                   NVL(c.COMMENTS, '') AS TABLE_COMMENT
            FROM (
                SELECT TABLE_NAME, 'TABLE' AS OBJECT_TYPE FROM ALL_TABLES WHERE OWNER = :param
                UNION ALL
                SELECT VIEW_NAME AS TABLE_NAME, 'VIEW' AS OBJECT_TYPE FROM ALL_VIEWS WHERE OWNER = :param
                UNION ALL
                SELECT MVIEW_NAME AS TABLE_NAME, 'MATERIALIZED VIEW' AS OBJECT_TYPE
                FROM ALL_MVIEWS WHERE OWNER = :param
            ) t
            LEFT JOIN ALL_TAB_COMMENTS c
                   ON t.TABLE_NAME = c.TABLE_NAME
                  AND c.TABLE_TYPE = t.OBJECT_TYPE
                  AND c.OWNER = :param
            ORDER BY t.TABLE_NAME
            """,
            {"param": schema or ""},
        )
    if key == "dm":
        return (
            """
            SELECT TABLE_NAME, COALESCE(COMMENTS, '') AS TABLE_COMMENT
            FROM ALL_TAB_COMMENTS
            WHERE OWNER = :param AND TABLE_TYPE IN ('TABLE', 'VIEW')
            ORDER BY TABLE_NAME
            """,
            {"param": schema or ""},
        )
    if key == "clickhouse":
        if legacy:
            return (
                """
                SELECT name AS TABLE_NAME, '' AS TABLE_COMMENT
                FROM system.tables
                WHERE database = :param AND engine NOT IN ('Dictionary')
                ORDER BY name
                """,
                {"param": database or "default"},
            )
        return (
            """
            SELECT name AS TABLE_NAME, comment AS TABLE_COMMENT
            FROM system.tables
            WHERE database = :param AND engine NOT IN ('Dictionary')
            ORDER BY name
            """,
            {"param": database or "default"},
        )
    raise ValueError(f"不支持的数据源类型: {db_type}")


def field_sql(
    db_type: Optional[str],
    database: Optional[str],
    schema: Optional[str],
    table_name: Optional[str] = None,
) -> FieldSql:
    """字段清单查询; 传入 table_name 时只查单表。"""
    key = normalize_db_type(db_type)
    if key in ("mysql", "doris", "starrocks"):
        sql = """
            SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE AS DATA_TYPE,
                   COALESCE(COLUMN_COMMENT, '') AS COLUMN_COMMENT, IS_NULLABLE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :param1
        """
        if table_name:
            sql += " AND TABLE_NAME = :param2"
        sql += " ORDER BY TABLE_NAME, ORDINAL_POSITION"
        return sql, {"param1": database or "", "param2": table_name}
    if key in ("postgresql", "redshift", "kingbase"):
        if key == "postgresql":
            # PostgreSQL 通过 pg_namespace 精确过滤 schema
            scope_from = """
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            """
            scope_where = "n.nspname = :param1"
        else:
            # Redshift/Kingbase 用子查询取 namespace, 避免额外的 join 语法差异
            scope_from = """
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            """
            scope_where = (
                "c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = :param1)"
            )
        sql = f"""
            SELECT c.relname AS TABLE_NAME,
                   a.attname AS COLUMN_NAME,
                   pg_catalog.format_type(a.atttypid, a.atttypmod) AS DATA_TYPE,
                   COALESCE(col_description(c.oid, a.attnum), '') AS COLUMN_COMMENT,
                   CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS IS_NULLABLE
            {scope_from}
            WHERE {scope_where}
              AND a.attnum > 0
              AND NOT a.attisdropped
        """
        if table_name:
            sql += " AND c.relname = :param2"
        sql += " ORDER BY c.relname, a.attnum"
        return sql, {"param1": schema or "public", "param2": table_name}
    if key == "sqlserver":
        sql = """
            SELECT C.TABLE_NAME, C.COLUMN_NAME, C.DATA_TYPE,
                   COALESCE(EP.value, '') AS COLUMN_COMMENT, C.IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS C
            LEFT JOIN sys.extended_properties EP
                   ON EP.major_id = OBJECT_ID(C.TABLE_SCHEMA + '.' + C.TABLE_NAME)
                  AND EP.minor_id = C.ORDINAL_POSITION
                  AND EP.name = 'MS_Description'
            WHERE C.TABLE_SCHEMA = :param1
        """
        if table_name:
            sql += " AND C.TABLE_NAME = :param2"
        sql += " ORDER BY C.TABLE_NAME, C.ORDINAL_POSITION"
        return sql, {"param1": schema or "dbo", "param2": table_name}
    if key == "oracle":
        sql = """
            SELECT col.TABLE_NAME,
                   col.COLUMN_NAME,
                   (CASE
                        WHEN col.DATA_TYPE IN ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR')
                            THEN col.DATA_TYPE || '(' || col.DATA_LENGTH || ')'
                        WHEN col.DATA_TYPE = 'NUMBER' AND col.DATA_PRECISION IS NOT NULL
                            THEN col.DATA_TYPE || '(' || col.DATA_PRECISION ||
                                 CASE WHEN col.DATA_SCALE > 0 THEN ',' || col.DATA_SCALE END || ')'
                        ELSE col.DATA_TYPE
                    END) AS DATA_TYPE,
                   NVL(com.COMMENTS, '') AS COLUMN_COMMENT,
                   col.NULLABLE AS IS_NULLABLE
            FROM ALL_TAB_COLUMNS col
            LEFT JOIN ALL_COL_COMMENTS com
                   ON col.OWNER = com.OWNER
                  AND col.TABLE_NAME = com.TABLE_NAME
                  AND col.COLUMN_NAME = com.COLUMN_NAME
            WHERE col.OWNER = :param1
        """
        if table_name:
            sql += " AND col.TABLE_NAME = :param2"
        sql += " ORDER BY col.TABLE_NAME, col.COLUMN_ID"
        return sql, {"param1": schema or "", "param2": table_name}
    if key == "dm":
        sql = """
            SELECT col.TABLE_NAME, col.COLUMN_NAME, col.DATA_TYPE,
                   COALESCE(com.COMMENTS, '') AS COLUMN_COMMENT,
                   col.NULLABLE AS IS_NULLABLE, col.DATA_DEFAULT AS DEFAULT_VALUE,
                   CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PRIMARY_KEY
            FROM ALL_TAB_COLUMNS col
            LEFT JOIN ALL_COL_COMMENTS com
                   ON col.OWNER = com.OWNER
                  AND col.TABLE_NAME = com.TABLE_NAME
                  AND col.COLUMN_NAME = com.COLUMN_NAME
            LEFT JOIN (
                SELECT cc.OWNER, cc.TABLE_NAME, cc.COLUMN_NAME
                FROM ALL_CONS_COLUMNS cc
                JOIN ALL_CONSTRAINTS con
                  ON cc.OWNER = con.OWNER
                 AND cc.TABLE_NAME = con.TABLE_NAME
                 AND cc.CONSTRAINT_NAME = con.CONSTRAINT_NAME
                WHERE con.CONSTRAINT_TYPE = 'P'
            ) pk ON col.OWNER = pk.OWNER
                AND col.TABLE_NAME = pk.TABLE_NAME
                AND col.COLUMN_NAME = pk.COLUMN_NAME
            WHERE col.OWNER = :param1
        """
        params = {"param1": schema or ""}
        if table_name is not None:
            sql += " AND col.TABLE_NAME = :param2"
            params["param2"] = table_name
        sql += " ORDER BY col.TABLE_NAME, col.COLUMN_ID"
        return sql, params
    if key == "clickhouse":
        sql = """
            SELECT table AS TABLE_NAME,
                   name AS COLUMN_NAME,
                   type AS DATA_TYPE,
                   comment AS COLUMN_COMMENT,
                   if(startsWith(type, 'Nullable'), 'YES', 'NO') AS IS_NULLABLE
            FROM system.columns
            WHERE database = :param1
        """
        if table_name:
            sql += " AND table = :param2"
        sql += " ORDER BY table, position"
        return sql, {"param1": database or "default", "param2": table_name}
    raise ValueError(f"不支持的数据源类型: {db_type}")
