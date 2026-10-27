"""LLM service: NL2SQL generation via OpenAI-compatible API.

- 使用 openai SDK 直连(支持 base_url 配置兼容 OpenAI 的中转/本地模型)
- 输出 JSON 健壮解析(容忍 markdown 代码块包裹)
- 未配置 API Key 时抛出 LLMServiceError, 由调用方降级处理
- 提供 embed_texts 供 RAG 向量化使用(无 Key 时返回 None)
"""
import json
import re
import logging
from typing import List, Tuple, Optional

from app.config import settings
from app.core.exceptions import LLMServiceError
from app.services.llm_config_service import LlmConfig, get_config, build_client, provider_error
from pydantic import SecretStr

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的数据分析师和SQL专家。根据用户的问题和数据库表结构，生成准确的SQL查询。

规则：
1. 只生成单条SELECT查询语句，禁止任何修改数据的操作
2. 使用与数据库兼容的标准SQL语法
3. 对聚合结果列使用中文别名（AS "销售额"）
4. 结尾必须带LIMIT（默认LIMIT 1000，排名类按需设置）
5. 结合对话上下文理解指代（如"再按月份看"）

{schema_section}

严格按以下JSON格式回复，不要输出其他内容：
{{"sql": "SELECT ...", "answer": "用一句话说明生成SQL的思路和结论"}}"""


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON(容忍 ```json 包裹、前后杂质)。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)


def _extract_sql_fallback(text: str) -> str:
    """JSON 解析失败时, 尝试直接提取 SQL 语句。"""
    fence = re.search(r"```(?:sql)?\s*(SELECT[\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    match = re.search(r"(SELECT[\s\S]+?)(?:;|$)", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _build_client(config: LlmConfig):
    return build_client(config)


def _build_messages(question: str, schema_prompt: str, history: list,
                    dialect_label: str = "") -> list:
    sections = []
    if dialect_label:
        sections.append(f"目标数据库: {dialect_label}，请使用该数据库的标准方言(标识符引用、日期函数、分页语法)。")
    if dialect_label == "达梦":
        sections.append(
            '达梦规则：使用 LIMIT count 或 LIMIT count OFFSET start 分页。'
            '模式、表、字段和别名使用双引号，模式与表分别引用，如 "schema"."table"。'
            '严格保留表结构中的标识符大小写，不把双引号内的名称转为大写或小写。'
        )
    if schema_prompt:
        sections.append(f"数据库表结构：\n{schema_prompt}")
    schema_section = "\n\n".join(sections)
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(schema_section=schema_section)}]
    for msg in (history or [])[-6:]:
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)
        if not role or not content:
            continue
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": content[:500]})
    messages.append({"role": "user", "content": question})
    return messages


async def generate_sql(
    question: str,
    schema_prompt: str = "",
    history: list = None,
    dialect_label: str = "",
) -> Tuple[str, str]:
    """
    自然语言 -> SQL。
    返回 (generated_sql, answer_text), 失败时抛出 LLMServiceError。
    """
    config = await get_config()
    try:
        async with _build_client(config) as client:
            response = await client.chat.completions.create(
                model=config.model,
                messages=_build_messages(question, schema_prompt, history, dialect_label),
                temperature=0.1,
                max_tokens=1500,
            )
    except LLMServiceError:
        raise
    except Exception as e:
        message = provider_error(e)
        logger.warning("LLM调用失败: %s", message)
        raise LLMServiceError(message) from None

    content = response.choices[0].message.content or "" if response.choices else ""
    try:
        result = _extract_json(content)
        sql = (result.get("sql") or "").strip()
        answer = (result.get("answer") or "").strip()
    except (json.JSONDecodeError, ValueError):
        sql = _extract_sql_fallback(content)
        answer = content[:300]
    if not sql:
        raise LLMServiceError("LLM未能生成有效SQL, 请尝试换一种问法")
    return sql, answer or "已根据表结构生成查询SQL"


async def chat_answer(question: str, history: list = None) -> str:
    """通用对话(寒暄/解释类问题)。失败时返回固定提示。"""
    try:
        config = await get_config()
        messages = [{"role": "system", "content": "你是智能问数平台的数据分析助手, 用简洁中文回答。"}]
        for msg in (history or [])[-6:]:
            if getattr(msg, "role", None) in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content[:500]})
        messages.append({"role": "user", "content": question})
        async with _build_client(config) as client:
            response = await client.chat.completions.create(
                model=config.model, messages=messages, temperature=0.5, max_tokens=800,
            )
        return response.choices[0].message.content or ""
    except Exception:
        return "您好!我是智能问数助手,请选择数据源后输入数据问题,例如:各区域销售额排名"


async def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """向量化文本。未配置 Key、被开关关闭或调用失败时返回 None(由调用方降级)。"""
    if not settings.llm_api_key or not settings.llm_embedding_enabled or not texts:
        return None
    try:
        # 向量化继续使用原有环境配置，不随聊天设置改变模型或索引维度。
        config = LlmConfig(settings.llm_base_url or "", settings.embedding_model,
                           SecretStr(settings.llm_api_key), "environment")
        async with _build_client(config) as client:
            response = await client.embeddings.create(
                model=settings.embedding_model, input=[t[:8000] for t in texts]
            )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.warning("Embedding调用失败: %s", provider_error(e))
        return None
