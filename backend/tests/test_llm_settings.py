"""模型配置权限、加密、热更新与供应商异常脱敏测试，不使用真实密钥。"""
import asyncio
import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.sql.elements import TextClause

from app import llm
from app.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import LLMServiceError, ValidationException
from app.database import get_db
from app.main import app
from app.models.log import OperationLog
from app.models.system_setting import SystemSetting
from app.models.user import Role, User
from app.schemas.schemas import LlmSettingsRequest
from app.services import llm_config_service as service

KEY = "sk-unit-test-not-a-real-key"
URL = "http://model.internal:8080/v1"
PATH = "/api/v1/admin/settings/llm"


def run(coro):
    return asyncio.run(coro)


class FakeDB:
    def __init__(self):
        self.record = None
        self.logs = []
        self.locks = 0
        self.flushes = 0
        self.reads = 0

    async def execute(self, statement):
        if isinstance(statement, TextClause):
            assert "pg_advisory_xact_lock" in str(statement)
            self.locks += 1
        else:
            self.reads += 1
        return SimpleNamespace(scalar_one_or_none=lambda: self.record)

    def add(self, record):
        if isinstance(record, SystemSetting):
            self.record = record
        else:
            assert isinstance(record, OperationLog)
            self.logs.append(record)

    async def flush(self):
        self.flushes += 1


class FakeClient:
    def __init__(self, error=None, content=None, choices=True):
        self.closed = False
        self.calls = []
        self.error = error
        self.response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=content or '{"sql":"SELECT 1","answer":"测试"}'))] if choices else [])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.embeddings = SimpleNamespace(create=self.embed)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response

    async def embed(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-unit-environment-only")
    monkeypatch.setattr(settings, "llm_base_url", "http://environment.internal/v1")
    monkeypatch.setattr(settings, "llm_model", "environment-model")
    return FakeDB()


@pytest.fixture
def api_client(env):
    previous = app.dependency_overrides.copy()
    user = User(id=uuid.uuid4(), username="test-admin", roles=[Role(name="admin")])

    async def db_override():
        yield env

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), env, user
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def payload(**kwargs):
    return {"base_url": URL, "model": "test-model", "api_key": KEY, **kwargs}


def test_environment_compatibility_and_public_state(env):
    config = run(service.get_config(env))
    public = run(service.describe_config(env))
    assert config.source == "environment" and config.model == "environment-model"
    assert public["has_api_key"] and public["key_readable"]
    assert "sk-unit" not in json.dumps(public)
    assert "api_key_enc" not in public and "api_key" not in public
    assert "sk-unit" not in repr(config)


def test_save_encryption_and_database_precedence(env):
    public = run(service.save_config(env, LlmSettingsRequest(**payload()), uuid.uuid4()))
    assert public["source"] == "database" and public["has_api_key"]
    assert env.record.id == 1 and env.locks == 1
    assert KEY.encode() not in env.record.api_key_enc
    assert service.decrypt_key(env.record.api_key_enc) == KEY
    assert KEY not in json.dumps(public) and "api_key_enc" not in public
    config = run(service.get_config(env))
    assert config.model == "test-model" and config.base_url == URL
    assert config.api_key.get_secret_value() == KEY


def test_blank_preserves_environment_then_saved_key(env):
    run(service.save_config(env, LlmSettingsRequest(**payload(api_key="")), uuid.uuid4()))
    assert service.decrypt_key(env.record.api_key_enc) == "sk-unit-environment-only"
    run(service.save_config(env, LlmSettingsRequest(**payload()), uuid.uuid4()))
    run(service.save_config(env, LlmSettingsRequest(model="new-model"), uuid.uuid4()))
    assert env.record.model == "new-model" and env.record.base_url == ""
    assert service.decrypt_key(env.record.api_key_enc) == KEY


def test_clear_does_not_fall_back_to_environment(env):
    run(service.save_config(env, LlmSettingsRequest(model="test", clear_api_key=True), uuid.uuid4()))
    assert env.record.api_key_enc is None
    assert not run(service.describe_config(env))["has_api_key"]
    run(service.save_config(env, LlmSettingsRequest(model="test"), uuid.uuid4()))
    assert not run(service.get_config(env)).api_key.get_secret_value()
    with pytest.raises(LLMServiceError):
        service.build_client(run(service.get_config(env)))


def test_strict_decryption_and_recovery(env):
    env.record = SystemSetting(id=1, base_url=URL, model="test", api_key_enc=b"plain-key",
                               updated_at=datetime.utcnow())
    with pytest.raises(LLMServiceError):
        run(service.get_config(env))
    public = run(service.describe_config(env))
    assert not public["key_readable"] and public["configuration_error"]
    assert "plain-key" not in json.dumps(public)
    run(service.save_config(env, LlmSettingsRequest(**payload()), uuid.uuid4()))
    assert run(service.describe_config(env))["key_readable"]
    env.record.api_key_enc = b"bad-token"
    run(service.save_config(env, LlmSettingsRequest(model="test", clear_api_key=True), uuid.uuid4()))
    assert env.record.api_key_enc is None


def test_key_derivation_change_rejects_old_cipher(monkeypatch):
    encrypted = service.encrypt_key(KEY)
    monkeypatch.setattr(settings, "jwt_secret", "different-unit-test-secret")
    with pytest.raises(LLMServiceError):
        service.decrypt_key(encrypted)


@pytest.mark.parametrize("url", [
    "ftp://example.com", "http://", "http://user:pass@example.com/v1", "https://example.com?key=private",
    "https://example.com/#private", "https://example.com:bad/v1", "https://example.com:0/v1",
    "https://example.com/v 1", "https://example.com/\\v1", "https://example.com/@bad?",
])
def test_invalid_urls_rejected(env, url):
    with pytest.raises(ValidationException):
        run(service.resolve_candidate(env, LlmSettingsRequest(**payload(base_url=url))))
    assert env.record is None and env.flushes == 0


@pytest.mark.parametrize("url", ["", "http://localhost:8080/v1", "https://api.example.com/v1/", "http://[::1]:8000/v1"])
def test_valid_urls_and_normalization(env, url):
    config = run(service.resolve_candidate(env, LlmSettingsRequest(**payload(base_url=url))))
    assert config.base_url == url.rstrip("/")


@pytest.mark.parametrize("changes", [{"model": "  "}, {"model": "bad\nmodel"},
                                      {"api_key": "bad key"}, {"clear_api_key": True}])
def test_invalid_input_or_conflicting_clear(env, changes):
    with pytest.raises(ValidationException):
        run(service.resolve_candidate(env, LlmSettingsRequest(**payload(**changes))))
    assert env.flushes == 0


@pytest.mark.parametrize("method,suffix", [("get", ""), ("put", ""), ("post", "/test")])
def test_routes_require_authentication(api_client, method, suffix):
    client, _, _ = api_client
    app.dependency_overrides.pop(get_current_user)
    kwargs = {"json": payload()} if method != "get" else {}
    assert getattr(client, method)(PATH + suffix, **kwargs).status_code == 401


@pytest.mark.parametrize("method,suffix", [("get", ""), ("put", ""), ("post", "/test")])
def test_routes_reject_non_admin(api_client, method, suffix):
    client, _, user = api_client
    user.roles = [Role(name="analyst")]
    kwargs = {"json": payload()} if method != "get" else {}
    assert getattr(client, method)(PATH + suffix, **kwargs).status_code == 403


def test_admin_save_get_and_safe_audit(api_client):
    client, db, user = api_client
    res = client.put(PATH, json=payload())
    assert res.status_code == 200 and res.json()["code"] == 0
    assert KEY not in res.text and "api_key_enc" not in res.text
    assert res.json()["data"]["updated_by"] == str(user.id)
    assert db.logs and db.logs[0].detail == {"has_api_key": True, "clear_api_key": False}
    assert KEY not in json.dumps(db.logs[0].detail)
    res = client.get(PATH)
    assert res.json()["data"]["model"] == "test-model" and KEY not in res.text


@pytest.mark.parametrize("body", [payload(api_key=KEY * 200), payload(api_key={"private": KEY}),
                                  {"model": [], "api_key": KEY}, payload(base_url="x" * 2049)])
def test_validation_errors_never_reflect_input(api_client, body):
    client, _, _ = api_client
    res = client.put(PATH, json=body)
    assert res.status_code == 422 and KEY not in res.text and "input" not in res.text


def test_malformed_json_is_not_reflected(api_client):
    client, _, _ = api_client
    res = client.post(PATH + "/test", content='{"api_key":"' + KEY + '"', headers={"Content-Type": "application/json"})
    assert res.status_code == 422 and KEY not in res.text


def test_probe_unsaved_form_and_client_closed(api_client, monkeypatch):
    client, db, _ = api_client
    fake = FakeClient()
    captured = []
    monkeypatch.setattr(service, "build_client", lambda config, timeout: captured.append((config, timeout)) or fake)
    res = client.post(PATH + "/test", json=payload())
    assert res.status_code == 200 and res.json()["code"] == 0
    assert res.json()["data"]["success"] and fake.closed
    assert db.record is None and not db.logs and db.flushes == 0 and db.locks == 0
    assert captured[0][0].base_url == URL and captured[0][0].api_key.get_secret_value() == KEY
    assert fake.calls[0]["model"] == "test-model" and fake.calls[0]["max_tokens"] == 8
    assert KEY not in res.text


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 400])
def test_provider_response_is_redacted(api_client, monkeypatch, status):
    from openai import APIStatusError
    client, db, _ = api_client
    error = APIStatusError(KEY, response=httpx.Response(status, request=httpx.Request("POST", URL)), body={"secret": KEY})
    fake = FakeClient(error=error)
    monkeypatch.setattr(service, "build_client", lambda *args, **kwargs: fake)
    res = client.post(PATH + "/test", json=payload())
    assert res.status_code == 200 and res.json()["code"] == 1
    assert not res.json()["data"]["success"] and fake.closed and db.record is None
    assert KEY not in res.text


@pytest.mark.parametrize("kind", ["connection", "timeout", "empty"])
def test_probe_network_timeout_or_empty_result(api_client, monkeypatch, kind):
    from openai import APIConnectionError, APITimeoutError
    client, _, _ = api_client
    request = httpx.Request("POST", URL)
    error = APIConnectionError(message=KEY, request=request) if kind == "connection" else APITimeoutError(request=request)
    fake = FakeClient(error=error if kind != "empty" else None, choices=kind != "empty")
    monkeypatch.setattr(service, "build_client", lambda *args, **kwargs: fake)
    res = client.post(PATH + "/test", json=payload())
    assert res.json()["code"] == 1 and fake.closed and KEY not in res.text


def test_probe_missing_key_reuses_current_but_clear_disables(env, monkeypatch):
    fake = FakeClient()
    captured = []
    real_builder = service.build_client
    monkeypatch.setattr(service, "build_client", lambda config, timeout: captured.append(config) or fake)
    result = run(service.probe_config(env, LlmSettingsRequest(model="test")))
    assert result["success"] and captured[0].api_key.get_secret_value() == "sk-unit-environment-only"
    monkeypatch.setattr(service, "build_client", real_builder)
    result = run(service.probe_config(env, LlmSettingsRequest(model="test", clear_api_key=True)))
    assert not result["success"] and env.record is None


def test_sql_and_chat_use_fresh_snapshots_and_close(monkeypatch):
    configs = [service.LlmConfig(URL, "first-model", SecretStr(KEY)),
               service.LlmConfig(URL, "second-model", SecretStr("sk-next-unit-key"))]
    reader = AsyncMock(side_effect=configs)
    clients = [FakeClient(), FakeClient(content="你好")]
    captured = []
    monkeypatch.setattr(llm, "get_config", reader)
    monkeypatch.setattr(llm, "_build_client", lambda config: captured.append(config) or clients[len(captured) - 1])
    assert run(llm.generate_sql("测试"))[0] == "SELECT 1"
    assert run(llm.chat_answer("你好")) == "你好"
    assert reader.await_count == 2
    assert clients[0].calls[0]["model"] == "first-model" and clients[1].calls[0]["model"] == "second-model"
    assert all(client.closed for client in clients)


def test_snapshot_reads_do_not_cache_or_mutate_old_value(env, monkeypatch):
    class SessionContext:
        async def __aenter__(self):
            return env
        async def __aexit__(self, *_):
            pass
    monkeypatch.setattr(service, "async_session_factory", SessionContext)
    first = run(service.get_config())
    run(service.save_config(env, LlmSettingsRequest(**payload()), uuid.uuid4()))
    second = run(service.get_config())
    assert first.source == "environment" and second.source == "database"
    assert first.model == "environment-model" and second.model == "test-model"


def test_sql_failure_redacts_logs_and_closes(monkeypatch, caplog):
    fake = FakeClient(error=RuntimeError(KEY))
    monkeypatch.setattr(llm, "get_config", AsyncMock(return_value=service.LlmConfig(URL, "test", SecretStr(KEY))))
    monkeypatch.setattr(llm, "_build_client", lambda _: fake)
    with pytest.raises(LLMServiceError) as exc:
        run(llm.generate_sql("测试"))
    assert KEY not in str(exc.value) and KEY not in caplog.text and fake.closed


def test_embedding_stays_on_environment_and_closes(env, monkeypatch):
    fake = FakeClient()
    captured = []
    monkeypatch.setattr(settings, "llm_embedding_enabled", True)
    monkeypatch.setattr(llm, "get_config", AsyncMock(side_effect=AssertionError("向量化不读取聊天配置")))
    monkeypatch.setattr(llm, "_build_client", lambda config: captured.append(config) or fake)
    assert run(llm.embed_texts(["测试"])) == [[0.1, 0.2]]
    assert captured[0].source == "environment" and captured[0].model == settings.embedding_model
    assert captured[0].api_key.get_secret_value() == "sk-unit-environment-only" and fake.closed


def test_builder_uses_explicit_default_url(monkeypatch):
    import openai
    captured = {}
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: captured.update(kwargs))
    service.build_client(service.LlmConfig("", "test", SecretStr(KEY)))
    assert captured["base_url"] == service.DEFAULT_BASE_URL and captured["max_retries"] == 0


@pytest.mark.parametrize("status", [200, 401])
def test_real_sdk_request_and_secret_redaction(env, monkeypatch, status):
    import openai
    original = openai.AsyncOpenAI
    clients = []
    requests = []

    def respond(request):
        requests.append(request)
        body = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]}
        if status != 200:
            body = {"error": {"message": KEY, "type": "authentication_error"}}
        return httpx.Response(status, json=body)

    def create(**kwargs):
        client = original(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", create)
    result = run(service.probe_config(env, LlmSettingsRequest(**payload())))
    assert result["success"] == (status == 200) and KEY not in json.dumps(result)
    assert str(requests[0].url) == URL + "/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer " + KEY
    assert json.loads(requests[0].content)["model"] == "test-model"
    assert clients[0].is_closed() and env.record is None


def test_postgresql_transactions_and_concurrent_updates(env, monkeypatch):
    """可选集成测试仅允许独立测试库，绝不连接业务数据库。"""
    import os
    from sqlalchemy import func, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app import database

    url = os.environ.get("DATQ_LLM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("未启用独立 PostgreSQL 测试库")
    parsed = make_url(url)
    assert parsed.database == "llm_config_test" and parsed.drivername == "postgresql+asyncpg"

    async def check():
        engine = create_async_engine(url, hide_parameters=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(service, "async_session_factory", factory)
        monkeypatch.setattr(database, "engine", engine)
        try:
            # 模拟 worker 同时启动，建表和补列应串行安全完成。
            await asyncio.gather(database.init_db(), database.init_db())
            user_id = uuid.uuid4()
            async with factory() as session:
                session.add(User(id=user_id, username="llm-unit-admin", email="unit@example.com", password_hash="unit-only"))
                await session.commit()

            async def write(model, key=""):
                async with factory() as session:
                    result = await service.save_config(session, LlmSettingsRequest(model=model, api_key=key), user_id)
                    await session.commit()
                    return result

            # 两个管理员首次保存并发时只能插入一条配置。
            await asyncio.gather(write("first-a", KEY), write("first-b", KEY))
            async with factory() as session:
                assert (await session.execute(select(func.count()).select_from(SystemSetting))).scalar() == 1
                stored = (await session.execute(select(SystemSetting))).scalar_one()
                assert KEY.encode() not in stored.api_key_enc
                assert service.decrypt_key(stored.api_key_enc) == KEY
            before = await service.get_config()
            await write("second-model")
            after = await service.get_config()
            assert before.model != after.model and after.model == "second-model"
            assert after.api_key.get_secret_value() == KEY

            # 新密钥更新与空密钥更新并发，无论顺序如何都不丢失新密钥。
            replacement = "sk-unit-concurrent-replacement"
            await asyncio.gather(write("replace-model", replacement), write("keep-model"))
            assert (await service.get_config()).api_key.get_secret_value() == replacement
            async with factory() as session:
                await service.save_config(session, LlmSettingsRequest(model="cleared", clear_api_key=True), user_id)
                await session.commit()
            assert not (await service.get_config()).api_key.get_secret_value()
        finally:
            await engine.dispose()

    run(check())
