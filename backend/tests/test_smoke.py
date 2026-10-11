"""冒烟测试: 验证应用可导入、核心路由已注册、健康检查与鉴权链路可用。

不依赖外部服务 (数据库/向量库/LLM), 只测应用装配本身, 适合 CI 快速反馈。
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _all_paths() -> set:
    """从 OpenAPI schema 收集全部路由路径 (兼容新版 FastAPI 的 _IncludedRouter 包装)。"""
    return set(app.openapi()["paths"].keys())


def test_app_imports():
    """应用模块可导入 (无语法错误/循环依赖/缺失依赖)。"""
    assert app is not None


def test_core_routes_registered():
    """核心业务路由已全部注册。"""
    paths = _all_paths()
    for expected in [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/query/ask",
        "/api/v1/datasources",
        "/api/v1/knowledge/docs",
        "/api/v1/knowledge/sql-examples",
        "/api/v1/admin/users",
        "/api/v1/admin/stats/query-trend",
        "/api/v1/semantic/models",
        "/api/v1/semantic/models/{model_id}/metrics",
        "/api/v1/semantic/models/{model_id}/dimensions",
        "/api/v1/conversations",
    ]:
        assert expected in paths, f"路由缺失: {expected}"


def test_health_endpoint():
    """健康检查端点可用。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_protected_endpoint_requires_token():
    """受保护接口未带 token 时应拒绝 (401), 证明鉴权链路生效。"""
    resp = client.get("/api/v1/admin/users")
    assert resp.status_code == 401


def test_sql_validator_blocks_non_select():
    """SQL 校验器应拦截非 SELECT 语句, 并给 SELECT 自动补 LIMIT。"""
    import pytest
    from app.engines.sql_validator import validate_and_fix, SQLSecurityError

    with pytest.raises(SQLSecurityError):
        validate_and_fix("DELETE FROM users")

    fixed, _ = validate_and_fix("SELECT 1")
    assert "limit" in fixed.lower()  # 强制行数限制已注入
