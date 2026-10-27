"""达梦原生接入回归测试：模拟 DBAPI，不依赖达梦实例、不修改演示库。"""
import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import engines
from app.engines import dm, metadata_sql
from app.engines.dialects import get_dialect, normalize_db_type, quote_identifier
from app.engines.sql_validator import validate_and_fix
from app.core.exceptions import SQLSecurityError, ValidationException
from app.schemas.schemas import DatasourceCreate, DatasourceProbe, DatasourceUpdate


class FakeLOB:
    def __init__(self, conn):
        self.conn = conn

    def read(self):
        assert not self.conn.closed, "大对象必须在连接关闭前读取"
        return "达梦大对象"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = []
        self.rows = []
        self.closed = False

    def execute(self, sql, params=None, *, timeout):
        driver = self.conn.driver
        driver.calls.append((sql, params, timeout))
        if sql == "SELECT 1 FROM DUAL":
            if self.conn.fail_ping:
                self.conn.fail_ping = False
                raise RuntimeError("失效连接")
            keys, rows = ["1"], [(1,)]
        elif sql.startswith("SET SCHEMA "):
            keys, rows = [], []
        elif "v$version" in sql:
            if driver.fail_version:
                raise RuntimeError("无权读取版本视图")
            keys, rows = ["BANNER"], [("DM Database Server 8",)]
        elif "object_type = 'SCH'" in sql:
            keys, rows = ["OBJECT_NAME"], [("Sales",), ("SYSDBA",), ("Sales",)]
        elif "FROM ALL_TAB_COMMENTS" in sql:
            assert params == {"param": "Sales"}
            keys, rows = ["TABLE_NAME", "TABLE_COMMENT"], [("Orders", "订单"), ("orders", "另一个表")]
        elif "FROM ALL_TAB_COLUMNS" in sql:
            assert params["param1"] == "Sales"
            assert "param2" not in params or ":param2" in sql
            keys = ["TABLE_NAME", "COLUMN_NAME", "DATA_TYPE", "COLUMN_COMMENT",
                    "IS_NULLABLE", "DEFAULT_VALUE", "IS_PRIMARY_KEY"]
            rows = [("Orders", "ID", "INTEGER", "主键", "N", "1", 1),
                    ("Orders", "Total", "DECIMAL", "金额", "Y", None, 0),
                    ("orders", "other", "VARCHAR", "另一个字段", "Y", None, 0)]
            if "param2" in params:
                rows = [row for row in rows if row[0] == params["param2"]]
        else:
            keys = ["Total", "created", "raw", "payload"]
            rows = [(Decimal("12.50"), date(2026, 1, 1), b"\x01\x02", FakeLOB(self.conn))]
            rows *= driver.query_row_count
        self.description = [(key, None) for key in keys]
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchmany(self, size):
        return self.rows[:size]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, driver):
        self.driver = driver
        self.closed = False
        self.fail_ping = False
        self.rollbacks = 0
        self.cursors = []

    def cursor(self):
        assert not self.closed
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeDriver:
    def __init__(self):
        self.connections = []
        self.configs = []
        self.calls = []
        self.fail_version = False
        self.query_row_count = 1

    def connect(self, **config):
        self.configs.append(config)
        conn = FakeConnection(self)
        self.connections.append(conn)
        return conn


@pytest.fixture
def source():
    return SimpleNamespace(id=uuid4(), db_type="dm", host="127.0.0.1", port=5236,
                           username="TEST_USER", password="test-only", db_schema="Sales",
                           database_name="", timeout=3, pool_size=2, pool_timeout=2,
                           extra_jdbc=None, name="测试达梦", description=None, status="inactive")


@pytest.fixture
def driver(monkeypatch, source):
    native = FakeDriver()
    monkeypatch.setattr(dm, "_load_driver", lambda: native)
    monkeypatch.setattr(engines, "create_engine", lambda *a, **k: pytest.fail("达梦不能进入 SQLAlchemy 驱动"))
    yield native
    for pool, _ in list(dm._pool_cache.values()):
        pool.dispose()
    dm._pool_cache.clear()


def test_type_registration_and_alias():
    assert normalize_db_type(" DaMeng ") == "dm"
    dialect = get_dialect("DM")
    assert dialect.default_port == 5236
    assert dialect.supports_schema and not dialect.supports_database
    assert not dialect.supports_ssl and not dialect.supports_connect_mode
    assert dialect.driver == "dmPython" and dialect.sqlglot is None


def test_pool_snapshot_reuse_and_configuration_change(driver, source):
    old = dm.get_pool(source)
    assert dm.get_pool(source) is old
    with dm.connection(source):
        pass
    assert driver.configs[0]["connection_timeout"] == 3
    assert driver.configs[0]["server"] == source.host
    assert "database" not in driver.configs[0]
    for key, value in [("password", "changed-test-only"), ("db_schema", "Other"),
                       ("pool_size", 3), ("pool_timeout", 4), ("extra_jdbc", "local_code=1")]:
        previous = dm.get_pool(source)
        setattr(source, key, value)
        assert dm.get_pool(source) is not previous
    assert driver.connections[0].closed


def test_pool_creator_does_not_capture_mutable_source(driver, source):
    pool = dm.get_pool(source)
    source.host = "changed.invalid"
    conn = pool.connect()
    conn.close()
    assert driver.configs[0]["server"] == "127.0.0.1"


def test_transient_and_encrypted_password(driver, source):
    source.id = None
    source.password = ""
    source.password_enc = engines.encrypt_password("encrypted-test-only")
    schemas = asyncio.run(engines.list_schemas(source))
    assert schemas == ["SYSDBA", "Sales"]
    assert not dm._pool_cache
    assert driver.configs[0]["password"] == "encrypted-test-only"
    assert driver.connections[0].closed
    assert all(cursor.closed for cursor in driver.connections[0].cursors)


def test_probe_is_uncached_and_returns_version(driver, source):
    result = asyncio.run(engines.test_connection(source))
    assert result["success"] and result["version"] == "DM Database Server 8"
    assert not dm._pool_cache
    assert driver.connections[0].closed


def test_version_permission_fallback(driver, source):
    driver.fail_version = True
    result = asyncio.run(engines.test_connection(source))
    assert result["success"] and result["version"] == ""
    assert any(sql == "SELECT 1 FROM DUAL" for sql, _, _ in driver.calls)


def test_stale_connection_replaced_and_disposed(driver, source):
    asyncio.run(engines.list_schemas(source))
    previous = driver.connections[0]
    previous.fail_ping = True
    assert asyncio.run(engines.list_schemas(source)) == ["SYSDBA", "Sales"]
    assert previous.closed and len(driver.connections) == 2
    engines.dispose_engine(source)
    assert driver.connections[1].closed and not dm._pool_cache


def test_metadata_and_primary_keys(driver, source):
    tables = asyncio.run(engines.list_tables(source))
    assert [table["table_name"] for table in tables] == ["Orders", "orders"]
    columns = asyncio.run(engines.list_columns(source, "Orders"))
    assert len(columns) == 2
    assert columns[0]["is_primary_key"] == 1 and columns[0]["is_nullable"] == 0
    assert columns[0]["default_value"] == "1"
    assert columns[1]["column_comment"] == "金额"
    sql, params = metadata_sql.field_sql("dm", None, "Sales", None)
    assert "col.OWNER = com.OWNER" in sql
    assert "cc.OWNER = con.OWNER" in sql
    assert "col.COLUMN_ID" in sql and params == {"param1": "Sales"}


def test_sync_exact_case_and_only_tables(driver, source):
    all_tables = asyncio.run(engines.sync_schema(source))
    assert len(all_tables[0]["columns"]) == 2 and len(all_tables[1]["columns"]) == 1
    assert "table_name" not in all_tables[0]["columns"][0]
    assert all_tables[0]["columns"][0]["is_primary_key"] == 1
    selected = asyncio.run(engines.sync_schema(source, ["orders"]))
    assert [table["table_name"] for table in selected] == ["orders"]
    assert selected[0]["columns"][0]["column_name"] == "other"


def test_query_serialization_percent_and_preview(driver, source):
    sql = 'SELECT "Total" FROM "Sales"."Orders" WHERE "Name" LIKE \'a%\' LIMIT 5'
    data, columns = asyncio.run(engines.execute_query(source, sql))
    assert data[0] == {"Total": 12.5, "created": "2026-01-01", "raw": "0102", "payload": "达梦大对象"}
    assert columns[0]["name"] == "Total"
    assert any(text == sql for text, _, _ in driver.calls)
    preview = asyncio.run(engines.preview_table(source, "Orders", 500))
    assert preview["row_count"] == 1
    assert any(text == 'SELECT * FROM "Sales"."Orders" LIMIT 200' for text, _, _ in driver.calls)


def test_max_rows_still_enforced(driver, source, monkeypatch):
    monkeypatch.setattr(engines.settings, "max_query_rows", 2)
    driver.query_row_count = 3
    with pytest.raises(RuntimeError, match="最大行数"):
        asyncio.run(engines.execute_query(source, "SELECT 1"))


@pytest.mark.parametrize("key", ["user", "password", "server", "port", "connection_timeout", "autoCommit"])
def test_reserved_extra_parameters_rejected(driver, source, key):
    source.extra_jdbc = f"{key}=override"
    with pytest.raises(ValueError, match="附加参数不能覆盖"):
        dm.get_pool(source)
    assert not driver.connections


def test_missing_driver_friendly_error(source, monkeypatch):
    monkeypatch.setattr(dm, "_load_driver", lambda: (_ for _ in ()).throw(ImportError("缺少驱动")))
    with pytest.raises(ConnectionError, match="dmPython==2.5.22"):
        asyncio.run(engines.test_connection(source))
    assert not dm._pool_cache


def test_schema_and_identifier_escaping(driver, source):
    source.db_schema = 'Sales"Data'
    assert engines.qualified_table_name(source, 'Mixed"Table') == '"Sales""Data"."Mixed""Table"'
    assert quote_identifier("dm", "MixedCase") == '"MixedCase"'
    asyncio.run(engines.list_schemas(source))
    assert any(text == 'SET SCHEMA "Sales""Data"' for text, _, _ in driver.calls)
    source.db_schema = ""
    with pytest.raises(RuntimeError, match="必须指定"):
        asyncio.run(engines.list_tables(source))
    with pytest.raises(RuntimeError, match="必须指定"):
        asyncio.run(engines.preview_table(source, "Orders"))


@pytest.mark.parametrize("sql", ["DELETE FROM x", "SELECT 1; DROP TABLE x", "SELECT SLEEP(1)",
                                 "SELECT * INTO new_table FROM old_table", " "])
def test_dm_sql_security(sql):
    with pytest.raises(SQLSecurityError):
        validate_and_fix(sql, "dm")


def test_dm_sql_limit_and_quotes():
    fixed, _ = validate_and_fix('SELECT "Amount" FROM "Sales"."Orders" LIMIT 5000', "dm", max_rows=10)
    assert '"Sales"."Orders"' in fixed and '"Amount"' in fixed
    assert "LIMIT 10" in fixed and "FETCH" not in fixed
    fixed, _ = validate_and_fix('SELECT "Amount" FROM "Sales"."Orders"', "dameng", max_rows=10)
    assert "LIMIT 10" in fixed


def test_dm_prompt_uses_exact_quoted_names():
    from app.api.v1.query import build_schema_prompt
    from app.llm import _build_messages
    tables = [SimpleNamespace(table_name="Orders", table_comment="订单")]
    columns = {"Orders": [SimpleNamespace(column_name="Total", column_type="DECIMAL", column_comment=None)]}
    prompt = build_schema_prompt(tables, columns, "Sales", "dm")
    assert '"Sales"."Orders"' in prompt and '"Total"' in prompt
    message = _build_messages("测试", prompt, [], "达梦")[0]["content"]
    assert "LIMIT count" in message and "严格保留" in message


def test_api_schema_validation_and_edit_password_reuse(source):
    from app.api.v1.datasource import _validate_schema, _probe_payload, create_datasource, update_datasource
    assert _validate_schema("dameng", " Sales ") == "Sales"
    assert _validate_schema("mysql", None) is None
    db = SimpleNamespace(execute=AsyncMock())
    data = DatasourceCreate(name="测试", db_type="dm", host="localhost", port=5236)
    with pytest.raises(ValidationException, match="必须指定"):
        asyncio.run(create_datasource(data, db=db))
    db.execute.assert_not_awaited()
    source.password_enc = engines.encrypt_password("stored-test-only")
    probe = DatasourceProbe(name="测试", db_type="dameng", host="localhost", port=5236, password="")
    assert _probe_payload(probe, source).password == "stored-test-only"
    assert _probe_payload(probe, source).db_type == "dm"


def test_update_cannot_clear_dm_schema(source, monkeypatch):
    from app.api.v1 import datasource
    monkeypatch.setattr(datasource, "_get_ds", AsyncMock(return_value=source))
    with pytest.raises(ValidationException, match="必须指定"):
        asyncio.run(datasource.update_datasource(source.id, DatasourceUpdate(db_schema=None), db=None))
    assert source.db_schema == "Sales"


def test_public_type_list_and_probe_route(driver):
    from app.main import app
    from app.database import get_db

    async def fake_db():
        yield None

    app.dependency_overrides[get_db] = fake_db
    try:
        client = TestClient(app)
        response = client.get("/api/v1/datasources/types")
        types = response.json()["data"]
        assert len(types) == 10
        assert next(item for item in types if item["db_type"] == "dm")["default_port"] == 5236
        response = client.post("/api/v1/datasources/test-connection", json={
            "name": "测试", "db_type": "dameng", "host": "localhost", "port": 5236,
            "username": "TEST_USER", "password": "test-only", "timeout": 1,
        })
        assert response.status_code == 200 and response.json()["data"]["success"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("db_type", ["dm", "mysql", "postgresql", "sqlserver", "oracle"])
def test_aggregate_queries_compatible_with_sqlglot(db_type):
    fixed, _ = validate_and_fix("SELECT SUM(amount) AS total FROM orders", db_type)
    assert "SUM" in fixed
    with pytest.raises(SQLSecurityError):
        validate_and_fix("SELECT SLEEP(1)", db_type)


def test_query_failure_invalidates_connection(driver, source, monkeypatch):
    original = FakeCursor.execute

    def fail(self, sql, params=None, *, timeout):
        if sql == "SELECT fail":
            raise RuntimeError("模拟查询失败")
        return original(self, sql, params, timeout=timeout)

    monkeypatch.setattr(FakeCursor, "execute", fail)
    with pytest.raises(RuntimeError, match="模拟查询失败"):
        asyncio.run(engines.execute_query(source, "SELECT fail"))
    assert driver.connections[0].closed
    assert all(cursor.closed for cursor in driver.connections[0].cursors)
    asyncio.run(engines.list_schemas(source))
    assert len(driver.connections) == 2
    assert driver.connections[1].rollbacks > 0


def test_transient_lob_query_serialized_before_close(driver, source):
    source.id = None
    data, _ = asyncio.run(engines.execute_query(source, "SELECT 1"))
    assert data[0]["payload"] == "达梦大对象"
    assert driver.connections[0].closed and not dm._pool_cache


def test_existing_format_driver_percent_escape_unchanged():
    seen = []
    conn = SimpleNamespace(dialect=SimpleNamespace(paramstyle="pyformat"),
                           exec_driver_sql=lambda sql: seen.append(sql))
    engines._exec_raw(conn, "SELECT * FROM t WHERE name LIKE 'a%'")
    assert seen == ["SELECT * FROM t WHERE name LIKE 'a%%'"]
