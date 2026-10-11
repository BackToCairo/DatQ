"""SQL 校验与自动修正引擎(基于 sqlglot)。

安全规则:
- 仅允许单条 SELECT/UNION 查询
- 拦截 DML/DDL/命令(INSERT/UPDATE/DELETE/DROP/...)与危险函数
- JOIN 数量、子查询嵌套深度限制
- 强制注入/收敛 LIMIT
- 列黑名单检查、行级权限过滤注入
"""
from typing import List, Dict, Optional, Tuple

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.core.exceptions import SQLSecurityError

SQL_DIALECT_MAP = {"postgresql": "postgres", "mysql": "mysql", "clickhouse": "clickhouse"}

# 危险函数黑名单
FORBIDDEN_FUNCTIONS = {
    "sleep", "pg_sleep", "pg_read_file", "pg_ls_dir", "lo_import", "lo_export",
    "load_file", "xp_cmdshell", "benchmark", "dblink", "copy", "pg_terminate_backend",
}

_ROW_FILTER_OPERATORS = {"eq", "neq", "in", "not_in", "like", "gt", "lt", "gte", "lte"}


def _dialect(db_type: Optional[str]) -> Optional[str]:
    if not db_type:
        return None
    return SQL_DIALECT_MAP.get(db_type)


def _parse(sql: str, dialect: Optional[str] = None) -> exp.Expression:
    try:
        parsed = sqlglot.parse_one(sql, read=_dialect(dialect))
    except ParseError as e:
        raise SQLSecurityError(f"SQL语法解析失败: {str(e)[:200]}")
    if parsed is None:
        raise SQLSecurityError("SQL语句为空")
    return parsed


def get_sql_tables(sql: str, db_type: Optional[str] = None) -> List[str]:
    """提取 SQL 引用的表名(小写)。"""
    parsed = _parse(sql, db_type)
    return sorted({t.name.lower() for t in parsed.find_all(exp.Table) if t.name})


def get_sql_columns(sql: str, db_type: Optional[str] = None) -> List[str]:
    """提取 SQL 引用的列名(小写)。"""
    parsed = _parse(sql, db_type)
    return sorted({c.name.lower() for c in parsed.find_all(exp.Column) if c.name})


def _check_forbidden_functions(parsed: exp.Expression) -> None:
    for node in parsed.find_all(exp.Func):
        name = getattr(node, "sql_name", "") or ""
        if name.lower() in FORBIDDEN_FUNCTIONS:
            raise SQLSecurityError(f"检测到危险函数: {name}")
    for anon in parsed.find_all(exp.Anonymous):
        if anon.name.lower() in FORBIDDEN_FUNCTIONS:
            raise SQLSecurityError(f"检测到危险函数: {anon.name}")


def _check_structure(parsed: exp.Expression, max_joins: int, max_subquery_depth: int) -> None:
    # 拦截一切 DML/DDL/命令节点
    forbidden_nodes = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
        exp.TruncateTable, exp.Merge, exp.Grant, exp.Command, exp.Set,
    )
    for node in parsed.find_all(*forbidden_nodes):
        raise SQLSecurityError(f"仅允许SELECT查询, 检测到: {node.key.upper()}")

    # JOIN 数量限制
    join_count = len(list(parsed.find_all(exp.Join)))
    if join_count > max_joins:
        raise SQLSecurityError(f"查询过于复杂: JOIN表数量({join_count})超过上限({max_joins})")

    # 子查询嵌套深度(SELECT节点数 - 1)
    depth = len(list(parsed.find_all(exp.Select))) - 1
    if depth > max_subquery_depth:
        raise SQLSecurityError(f"子查询嵌套过深({depth}层), 上限{max_subquery_depth}层")


def _enforce_limit(parsed: exp.Expression, max_rows: int, warnings: List[str]) -> exp.Expression:
    existing = parsed.args.get("limit")
    if existing is None:
        parsed = parsed.limit(max_rows)
        warnings.append(f"未指定LIMIT, 已自动追加LIMIT {max_rows}")
    else:
        try:
            current = int(existing.expression.name)
        except (ValueError, AttributeError):
            current = max_rows
        if current > max_rows:
            parsed = parsed.limit(max_rows)
            warnings.append(f"LIMIT {current} 超过上限, 已收敛为 {max_rows}")
    return parsed


def _check_column_blacklist(parsed: exp.Expression, blacklist: List[Dict]) -> None:
    """blacklist: [{"table_name": "t", "column_name": "c"}, ...](小写)"""
    if not blacklist:
        return
    black_set = {(b["table_name"].lower(), b["column_name"].lower()) for b in blacklist}
    for col in parsed.find_all(exp.Column):
        col_name = (col.name or "").lower()
        table_name = (col.table or "").lower()
        if not col_name:
            continue
        for bt, bc in black_set:
            if col_name == bc and (not table_name or not bt or table_name == bt):
                raise SQLSecurityError(f"字段 {table_name + '.' if table_name else ''}{col_name} 已被限制访问")


def _build_filter_condition(f: Dict) -> exp.Expression:
    column = exp.column(f["filter_column"], table=f.get("table_name") or None)
    value = f["filter_value"]
    op = f["filter_operator"]
    if op == "eq":
        return exp.EQ(this=column, expression=exp.Literal.string(value))
    if op == "neq":
        return exp.NEQ(this=column, expression=exp.Literal.string(value))
    if op == "like":
        return exp.Like(this=column, expression=exp.Literal.string(f"%{value}%"))
    if op in ("gt", "gte", "lt", "lte"):
        cls = {"gt": exp.GT, "gte": exp.GTE, "lt": exp.LT, "lte": exp.LTE}[op]
        return cls(this=column, expression=exp.Literal.string(value))
    if op in ("in", "not_in"):
        values = [v.strip() for v in str(value).split(",") if v.strip()]
        exprs = [exp.Literal.string(v) for v in values]
        in_expr = exp.In(this=column, expressions=exprs)
        return exp.Not(this=in_expr) if op == "not_in" else in_expr
    raise SQLSecurityError(f"不支持的行权限操作符: {op}")


def inject_row_filters(
    sql: str,
    row_filters: List[Dict],
    db_type: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """将行级权限过滤条件以 AND 方式注入 WHERE 子句。"""
    if not row_filters:
        return sql, []
    parsed = _parse(sql, db_type)
    conditions = []
    for f in row_filters:
        if f.get("filter_operator") not in _ROW_FILTER_OPERATORS:
            continue
        conditions.append(_build_filter_condition(f))
    if not conditions:
        return sql, []
    combined = conditions[0]
    for c in conditions[1:]:
        combined = exp.And(this=combined, expression=c)
    existing_where = parsed.args.get("where")
    if existing_where is not None:
        new_cond = exp.And(this=existing_where.this, expression=combined)
        parsed.set("where", exp.Where(this=new_cond))
    else:
        parsed.set("where", exp.Where(this=combined))
    return parsed.sql(dialect=_dialect(db_type)), [f"已注入 {len(conditions)} 条行级权限过滤"]


def validate_and_fix(
    sql: str,
    db_type: Optional[str] = None,
    max_rows: int = 1000,
    max_joins: int = 5,
    max_subquery_depth: int = 3,
    column_blacklist: Optional[List[Dict]] = None,
) -> Tuple[str, List[str]]:
    """
    校验并自动修正 SQL。
    返回 (修正后的SQL, warnings列表), 不通过时抛出 SQLSecurityError。
    """
    warnings: List[str] = []

    # 多语句检查
    try:
        statements = sqlglot.parse(sql, read=_dialect(db_type))
        statements = [s for s in statements if s is not None]
    except ParseError as e:
        raise SQLSecurityError(f"SQL语法解析失败: {str(e)[:200]}")
    if len(statements) > 1:
        raise SQLSecurityError("不允许一次执行多条SQL语句")

    parsed = statements[0]
    root_key = parsed.key
    if root_key not in ("select", "union", "subquery"):
        raise SQLSecurityError(f"仅允许SELECT查询, 检测到: {root_key.upper()}")

    _check_forbidden_functions(parsed)
    _check_structure(parsed, max_joins, max_subquery_depth)
    if column_blacklist:
        _check_column_blacklist(parsed, column_blacklist)

    parsed = _enforce_limit(parsed, max_rows, warnings)
    fixed_sql = parsed.sql(dialect=_dialect(db_type))
    return fixed_sql, warnings


def quick_select_check(sql: str) -> bool:
    """轻量级 SELECT 检查(用于 sqlglot 不可用或解析失败时的兜底)。"""
    s = sql.strip().rstrip(";").strip()
    if not s.upper().startswith("SELECT") and not s.upper().startswith("WITH"):
        return False
    banned = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
              "GRANT", "REVOKE", "MERGE", "EXEC", "EXECUTE", "INTO OUTFILE")
    upper = s.upper()
    return not any(b in upper for b in banned)
