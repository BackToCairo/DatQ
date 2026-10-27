"""多数据源方言注册表(移植自 SQLBot `apps/db/constant.py`)。

集中描述每一种可接入的数据源: 默认端口、SQLAlchemy 驱动、sqlglot 方言、
建连参数以及表单需要的能力标记(schema/SSL/Oracle 连接模式/低版本兼容)。

连接构建、元数据探测、SQL 校验和前端表单都从这里读取配置,
新增一种数据库只需在本文件登记一条 DbDialect。
"""
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DbDialect:
    """单个数据源类型的连接能力描述。"""

    db_type: str                      # 内部类型标识(入库值)
    label: str                        # 展示名称
    default_port: int                 # 默认端口
    driver: str                       # SQLAlchemy 驱动前缀
    sqlglot: Optional[str] = None     # sqlglot 方言名
    default_schema: str = ""          # 默认 schema/owner
    supports_schema: bool = False     # 是否需要填写 schema
    supports_database: bool = True    # 是否需要填写数据库名
    supports_ssl: bool = False        # 是否支持 SSL 开关
    supports_connect_mode: bool = False   # 是否需要 service_name/sid 选择
    supports_low_version: bool = False    # 是否需要低版本兼容开关
    driver_package: str = ""          # 缺失时提示安装的 pip 包
    accent: str = "#6366f1"           # 前端标签配色

    def to_dict(self) -> Dict:
        return asdict(self)


# 注册顺序即前端展示顺序
DIALECTS: Dict[str, DbDialect] = {
    d.db_type: d
    for d in [
        DbDialect(
            db_type="mysql", label="MySQL", default_port=3306,
            driver="mysql+pymysql", sqlglot="mysql",
            supports_ssl=True, driver_package="pymysql", accent="#4479A1",
        ),
        DbDialect(
            db_type="postgresql", label="PostgreSQL", default_port=5432,
            driver="postgresql+psycopg2", sqlglot="postgres",
            default_schema="public", supports_schema=True,
            driver_package="psycopg2-binary", accent="#336791",
        ),
        DbDialect(
            db_type="clickhouse", label="ClickHouse", default_port=8123,
            driver="clickhouse+http", sqlglot="clickhouse",
            driver_package="clickhouse-sqlalchemy", accent="#FFCC00",
        ),
        DbDialect(
            db_type="sqlserver", label="SQL Server", default_port=1433,
            driver="mssql+pymssql", sqlglot="tsql",
            supports_schema=True, supports_low_version=True,
            driver_package="pymssql", accent="#CC2132",
        ),
        DbDialect(
            db_type="oracle", label="Oracle", default_port=1521,
            driver="oracle+oracledb", sqlglot="oracle",
            supports_schema=True, supports_connect_mode=True,
            driver_package="oracledb", accent="#F80000",
        ),
        DbDialect(
            db_type="doris", label="Apache Doris", default_port=9030,
            driver="mysql+pymysql", sqlglot="mysql",
            supports_ssl=True, driver_package="pymysql", accent="#f59e0b",
        ),
        DbDialect(
            db_type="starrocks", label="StarRocks", default_port=9030,
            driver="mysql+pymysql", sqlglot="mysql",
            supports_ssl=True, driver_package="pymysql", accent="#7c3aed",
        ),
        DbDialect(
            db_type="redshift", label="AWS Redshift", default_port=5439,
            driver="postgresql+psycopg2", sqlglot="postgres",
            supports_schema=True, driver_package="psycopg2-binary", accent="#8b5cf6",
        ),
        DbDialect(
            db_type="kingbase", label="Kingbase", default_port=54321,
            driver="postgresql+psycopg2", sqlglot="postgres",
            supports_schema=True, driver_package="psycopg2-binary", accent="#0ea5e9",
        ),
        DbDialect(
            db_type="dm", label="达梦", default_port=5236,
            driver="dmPython", sqlglot=None,
            supports_schema=True, supports_database=False,
            driver_package="dmPython==2.5.22", accent="#D71920",
        ),
    ]
}

# 兼容 SQLBot/其他系统使用的类型别名
_TYPE_ALIASES = {
    "pg": "postgresql",
    "postgres": "postgresql",
    "ck": "clickhouse",
    "mssql": "sqlserver",
    "sql_server": "sqlserver",
    "sql server": "sqlserver",
    "mysql5": "mysql",
    "mariadb": "mysql",
    "dameng": "dm",
}

# 不同数据库的标识符引用符
_IDENTIFIER_QUOTES: Dict[str, tuple] = {
    "sqlserver": ("[", "]"),
    "mysql": ("`", "`"),
    "doris": ("`", "`"),
    "starrocks": ("`", "`"),
}
_DEFAULT_QUOTES = ('"', '"')

# 不允许通过「附加连接参数」注入的键(mysql 本地文件读取)
FORBIDDEN_EXTRA_PARAMS: Dict[str, set] = {"mysql": {"local_infile"}}


def normalize_db_type(db_type: Optional[str]) -> str:
    """归一化数据源类型标识。"""
    value = (db_type or "").strip()
    key = value.lower()
    return _TYPE_ALIASES.get(key, key)


def get_dialect(db_type: Optional[str]) -> DbDialect:
    """获取数据源类型描述，未支持的类型抛 ValueError。"""
    key = normalize_db_type(db_type)
    dialect = DIALECTS.get(key)
    if not dialect:
        supported = ", ".join(d.label for d in DIALECTS.values())
        raise ValueError(f"不支持的数据源类型: {db_type}，当前支持: {supported}")
    return dialect


def is_supported(db_type: Optional[str]) -> bool:
    return normalize_db_type(db_type) in DIALECTS


def list_dialects() -> List[Dict]:
    """供前端读取的类型清单。"""
    return [d.to_dict() for d in DIALECTS.values()]


def quote_identifier(db_type: Optional[str], name: str) -> str:
    """按数据库方言引用标识符。"""
    db_type = normalize_db_type(db_type)
    if db_type == "oracle":
        # Oracle 未加引号的标识符会折叠为大写, 统一大写后再引用以兼容常规对象
        name = name.upper()
    left, right = _IDENTIFIER_QUOTES.get(db_type, _DEFAULT_QUOTES)
    escaped = name.replace(right, right * 2)
    return f"{left}{escaped}{right}"


def split_extra_params(db_type: Optional[str], raw: Optional[str]) -> Dict[str, str]:
    """解析 `k1=v1&k2=v2` 形式的附加连接参数。"""
    if not raw:
        return {}
    forbidden = FORBIDDEN_EXTRA_PARAMS.get(normalize_db_type(db_type), set())
    params: Dict[str, str] = {}
    for chunk in str(raw).split("&"):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        key, value = key.strip(), value.strip()
        if not key or value == "":
            raise ValueError(f"附加参数格式错误: {chunk}，应为 k=v")
        if key in forbidden:
            raise ValueError(f"不允许的连接参数: {key}")
        params[key] = value
    return params


def build_query_string(params: Dict[str, str]) -> str:
    return "&".join(
        f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in params.items()
    )
