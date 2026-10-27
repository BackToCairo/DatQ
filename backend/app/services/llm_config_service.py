"""大模型配置快照、严格密钥加解密及不落库的连接测试。"""
import asyncio
import base64
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import LLMServiceError, ValidationException
from app.database import async_session_factory
from app.models.system_setting import SystemSetting
from app.schemas.schemas import LlmSettingsRequest

DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    model: str
    api_key: SecretStr = field(repr=False)
    source: str = "database"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_key(key: str) -> bytes | None:
    return _fernet().encrypt(key.encode()) if key else None


def decrypt_key(stored: bytes | None) -> str:
    if not stored:
        return ""
    try:
        return _fernet().decrypt(bytes(stored)).decode()
    except (InvalidToken, UnicodeError, TypeError, ValueError):
        # 不接受明文回退，也不静默回退到环境变量。
        raise LLMServiceError("已保存的 API Key 无法解密，请管理员重新填写或清除密钥") from None


async def _get_record(db: AsyncSession) -> SystemSetting | None:
    result = await db.execute(select(SystemSetting).execution_options(populate_existing=True))
    return result.scalar_one_or_none()


def _snapshot(record: SystemSetting | None) -> LlmConfig:
    if record is None:
        return LlmConfig(settings.llm_base_url or "", settings.llm_model,
                         SecretStr(settings.llm_api_key or ""), "environment")
    return LlmConfig(record.base_url, record.model, SecretStr(decrypt_key(record.api_key_enc)))


async def get_config(db: AsyncSession | None = None) -> LlmConfig:
    """每次调用新读数据库，不缓存进程内配置，正在执行的请求保持其快照。"""
    if db is not None:
        return _snapshot(await _get_record(db))
    async with async_session_factory() as session:
        return _snapshot(await _get_record(session))


async def describe_config(db: AsyncSession) -> dict:
    record = await _get_record(db)
    if record is None:
        config = _snapshot(None)
        return {"base_url": config.base_url, "model": config.model,
                "has_api_key": bool(config.api_key.get_secret_value()), "key_readable": True,
                "source": config.source, "updated_at": None, "updated_by": None,
                "configuration_error": None}
    error = None
    try:
        decrypt_key(record.api_key_enc)
    except LLMServiceError as exc:
        error = exc.message
    return {"base_url": record.base_url, "model": record.model,
            "has_api_key": bool(record.api_key_enc), "key_readable": error is None,
            "source": "database", "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "updated_by": str(record.updated_by) if record.updated_by else None,
            "configuration_error": error}


def _validate(data: LlmSettingsRequest) -> tuple[str, str, str]:
    base_url, model = data.base_url.strip(), data.model.strip()
    key = data.api_key.get_secret_value().strip() if data.api_key is not None else ""
    if not model or len(model) > 128 or any(ord(c) < 32 for c in model):
        raise ValidationException("请输入有效模型名（最多 128 个字符）")
    if base_url:
        try:
            parts = urlsplit(base_url)
            port = parts.port
            valid = (parts.scheme in ("http", "https") and parts.hostname
                     and not parts.username and not parts.password
                     and "@" not in parts.netloc and "?" not in base_url and "#" not in base_url
                     and (port is None or 1 <= port <= 65535)
                     and len(base_url) <= 2048
                     and not any(c.isspace() or ord(c) < 32 or c == "\\" for c in base_url))
        except ValueError:
            valid = False
        if not valid:
            raise ValidationException("API 地址仅支持 HTTP/HTTPS，不能包含账号密码、查询参数或片段")
        base_url = base_url.rstrip("/")
    if len(key) > 4096 or any(c.isspace() or ord(c) < 32 for c in key):
        raise ValidationException("API Key 格式无效")
    if data.clear_api_key and key:
        raise ValidationException("不能同时填写和清除 API Key")
    return base_url, model, key


async def resolve_candidate(db: AsyncSession, data: LlmSettingsRequest) -> LlmConfig:
    base_url, model, key = _validate(data)
    if data.clear_api_key:
        key = ""
    elif not key:
        key = (await get_config(db)).api_key.get_secret_value()
    return LlmConfig(base_url, model, SecretStr(key))


async def save_config(db: AsyncSession, data: LlmSettingsRequest, user_id) -> dict:
    _validate(data)
    # 首次插入和留空保留密钥也参与串行写入，避免并发更新覆盖另一个管理员的密钥。
    await db.execute(text("SELECT pg_advisory_xact_lock(681947201)"))
    config = await resolve_candidate(db, data)
    record = await _get_record(db)
    if record is None:
        record = SystemSetting(id=1)
        db.add(record)
    record.base_url = config.base_url
    record.model = config.model
    record.api_key_enc = encrypt_key(config.api_key.get_secret_value())
    record.updated_by = user_id
    record.updated_at = datetime.utcnow()
    await db.flush()
    return await describe_config(db)


def build_client(config: LlmConfig, timeout: int = 60):
    if not config.api_key.get_secret_value():
        raise LLMServiceError("LLM API Key 未配置，请在系统设置中配置后重试")
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=config.api_key.get_secret_value(),
                       base_url=config.base_url or DEFAULT_BASE_URL,
                       timeout=timeout, max_retries=0)


def provider_error(exc: Exception) -> str:
    """只使用异常类型/状态码，供应商响应可能反射密钥，不能回传或记录原文。"""
    from openai import APITimeoutError, APIConnectionError
    if isinstance(exc, (APITimeoutError, asyncio.TimeoutError)):
        return "模型连接超时，请检查 API 地址或稍后重试"
    if isinstance(exc, APIConnectionError):
        return "无法连接模型服务，请检查 API 地址和网络"
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "模型服务认证失败，请检查 API Key 和访问权限"
    if status == 404:
        return "模型或接口不存在，请检查模型名及 API 地址（通常包含 /v1）"
    if status == 429:
        return "模型服务额度不足或请求过于频繁，请检查账户额度"
    if isinstance(status, int) and status >= 500:
        return "模型服务暂时不可用，请稍后重试"
    return "模型请求失败，请检查模型名、接口地址及供应商状态"


async def probe_config(db: AsyncSession, data: LlmSettingsRequest) -> dict:
    config = await resolve_candidate(db, data)
    start = time.monotonic()
    try:
        async with build_client(config, timeout=15) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=config.model, messages=[{"role": "user", "content": "回复 OK"}],
                max_tokens=8, stream=False,
            ), timeout=15)
            if not response.choices:
                raise LLMServiceError("模型服务未返回有效结果，请检查接口兼容性")
        success, message = True, "模型连接成功（仅测试，配置未保存）"
    except LLMServiceError as exc:
        success, message = False, exc.message
    except Exception as exc:
        success, message = False, provider_error(exc)
    return {"success": success, "message": message,
            "latency_ms": round((time.monotonic() - start) * 1000)}
