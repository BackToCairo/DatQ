"""Query API routes - NL2SQL core engine."""
import logging
import uuid
import time
import json
import io
import csv
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy import delete as sql_delete
from app.database import get_db
from app.config import settings
from app.models.user import User, ColumnBlacklist, RowFilter
from app.models.conversation import Conversation, ConversationMessage
from app.models.datasource import Datasource, TableMetadata, ColumnMetadata
from app.models.log import QueryLog
from app.models.knowledge import SqlExample
from app.schemas.schemas import (
    QueryAskRequest, QueryResultResponse, QueryExecuteRequest,
    QueryFeedbackRequest, ApiResponse
)
from app.core.deps import get_optional_user
from app.core.ratelimit import check_rate_limit
from app.core.exceptions import (
    NotFoundException, NL2SQLGenerationError, SQLExecutionError,
    SQLSecurityError, DatasourceConnectionError, LLMServiceError
)
from app.services import rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["问数"])

# Dangerous SQL keywords to block
BLOCKED_KEYWORDS = [
    "DROP", "TRUNCATE", "ALTER", "CREATE", "DELETE", "INSERT",
    "UPDATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE"
]


def validate_sql_safety(sql: str) -> bool:
    """Basic SQL safety check - only allow SELECT statements."""
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return False
    for keyword in BLOCKED_KEYWORDS:
        if keyword in sql_upper.split():
            return False
    return True


def build_schema_prompt(tables: list, columns_map: dict) -> str:
    """Build schema prompt from table/column metadata for LLM."""
    prompt_parts = []
    for table in tables:
        tname = table.table_name
        cols = columns_map.get(tname, [])
        col_desc = []
        for c in cols:
            desc = f"  - {c.column_name} ({c.column_type})"
            if c.column_comment:
                desc += f" -- {c.column_comment}"
            col_desc.append(desc)
        table_desc = f"表: {tname}"
        if table.table_comment:
            table_desc += f" -- {table.table_comment}"
        prompt_parts.append(f"{table_desc}\n" + "\n".join(col_desc))
    return "\n\n".join(prompt_parts)


@router.post("/ask", response_model=ApiResponse)
async def ask_question(
    data: QueryAskRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    核心问数接口：自然语言 -> RAG检索 -> SQL生成 -> 校验修正 -> 执行查询 -> 结果/图表
    支持上下文追问（通过 conversation_id 关联历史）
    """
    start_time = time.time()

    # 1. 限流 + 获取用户
    user = current_user
    check_rate_limit(f"ask:{user.id if user else 'anonymous'}")

    # 2. 获取或创建会话
    conv = None
    if data.conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == data.conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise NotFoundException("会话不存在")
    else:
        # Auto create conversation
        conv = Conversation(
            user_id=user.id if user else None,
            title=data.question[:50],
        )
        db.add(conv)
        await db.flush()
        await db.refresh(conv)

    # 3. 保存用户消息
    user_msg = ConversationMessage(
        conversation_id=conv.id,
        role="user",
        content=data.question,
    )
    db.add(user_msg)

    # 4. 获取数据源和表结构
    ds = None
    schema_prompt = ""
    if data.datasource_id:
        result = await db.execute(
            select(Datasource).where(Datasource.id == data.datasource_id)
        )
        ds = result.scalar_one_or_none()
        if not ds:
            raise NotFoundException("数据源不存在")

        # Load table metadata
        result = await db.execute(
            select(TableMetadata).where(TableMetadata.datasource_id == ds.id)
        )
        tables = result.scalars().all()

        columns_map = {}
        for t in tables:
            result = await db.execute(
                select(ColumnMetadata).where(ColumnMetadata.table_id == t.id)
            )
            columns_map[t.table_name] = result.scalars().all()

        schema_prompt = build_schema_prompt(tables, columns_map)

    # 5. 获取历史对话上下文
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(10)
    )
    history_messages = list(reversed(result.scalars().all()))

    # 5.5 RAG 检索: DDL/业务文档/SQL示例 + 权限上下文
    rag_ctx = {"ddl_schemas": [], "knowledge_docs": [], "sql_examples": []}
    try:
        rag_ctx = await rag_service.retrieve(data.question, top_k=5,
                                             datasource_id=str(ds.id) if ds else None)
    except Exception:
        pass
    rag_sections = []
    if rag_ctx.get("knowledge_docs"):
        docs_text = "\n\n".join(d["content"][:400] for d in rag_ctx["knowledge_docs"][:3])
        rag_sections.append(f"业务知识参考:\n{docs_text}")
    if rag_ctx.get("ddl_schemas"):
        ddl_text = "\n\n".join(d["content"][:300] for d in rag_ctx["ddl_schemas"][:2])
        rag_sections.append(f"相关表DDL参考:\n{ddl_text}")
    full_schema_prompt = "\n\n".join([p for p in [schema_prompt] + rag_sections if p])

    # 6. NL2SQL generation (LLM call, 失败时降级: 知识库示例匹配 -> 占位提示)
    generated_sql = ""
    llm_answer = ""
    llm_degraded = False
    try:
        from app.llm import generate_sql
        generated_sql, llm_answer = await generate_sql(
            question=data.question,
            schema_prompt=full_schema_prompt,
            history=history_messages,
        )
    except LLMServiceError as e:
        llm_degraded = True
        # 降级: 从知识库 SQL 示例中匹配最相似的问题。
        # RAG上下文优先; 若向量库不可用/未命中, 直查数据库兜底, 保证降级路径可用。
        q_lower = data.question.lower()

        def _overlap(ex_q: str) -> float:
            ex_q = (ex_q or "").lower()
            if not ex_q:
                return 0.0
            return len(set(q_lower) & set(ex_q)) / max(1, len(set(q_lower) | set(ex_q)))

        candidates = []
        for ex in rag_ctx.get("sql_examples", []):
            meta = ex.get("metadata") or {}
            candidates.append((meta.get("question", ""), ex.get("content", "")))
        db_examples = (await db.execute(
            select(SqlExample).where(SqlExample.status == "active").limit(50)
        )).scalars().all()
        for ex in db_examples:
            candidates.append((ex.question, f"问题: {ex.question}\nSQL:\n{ex.sql_content}"))

        matched, best_score = None, 0.0
        for ex_q, ex_content in candidates:
            overlap = _overlap(ex_q)
            if overlap > best_score:
                best_score, matched = overlap, {"question": ex_q, "content": ex_content}

        if matched and best_score >= 0.25:
            generated_sql = matched["content"].split("SQL:\n")[-1].strip()
            llm_answer = (f"当前未配置LLM服务，已从知识库匹配到近似示例「{matched['question']}」并直接执行。"
                          f"配置LLM后可获得更准确的生成效果。")
        else:
            generated_sql = ""
            llm_answer = (f"{e}。未能在知识库中匹配到相似示例，请先在知识库中维护SQL示例，"
                          f"或配置LLM API Key后重试。")
            logger.warning("降级未匹配: candidates=%d best_score=%.3f question=%r",
                           len(candidates), best_score, data.question)
    except Exception as e:
        llm_degraded = True
        generated_sql = ""
        llm_answer = f"SQL生成过程出现异常: {str(e)}，请稍后重试或联系管理员。"

    # 6.5 SQL 校验与修正(sqlglot) + 行/列权限
    sql_warnings = []
    if generated_sql and ds:
        # 采集当前用户角色的列黑名单与行权限
        blacklist = []
        row_filters = []
        if user:
            role_ids = [r.id for r in (user.roles or [])]
            if role_ids:
                bl_rows = (await db.execute(
                    select(ColumnBlacklist).where(ColumnBlacklist.role_id.in_(role_ids))
                )).scalars().all()
                blacklist = [{"table_name": b.table_name, "column_name": b.column_name} for b in bl_rows]
                rf_rows = (await db.execute(
                    select(RowFilter).where(RowFilter.role_id.in_(role_ids))
                )).scalars().all()
                row_filters = [{"table_name": r.table_name, "filter_column": r.filter_column,
                                "filter_operator": r.filter_operator, "filter_value": r.filter_value}
                               for r in rf_rows]
        try:
            from app.engines.sql_validator import validate_and_fix, inject_row_filters
            generated_sql, sql_warnings = await validate_and_fix(
                generated_sql, db_type=ds.db_type,
                max_rows=settings.max_query_rows,
                column_blacklist=blacklist,
            )
            generated_sql, perm_warnings = await inject_row_filters(generated_sql, row_filters, ds.db_type)
            sql_warnings.extend(perm_warnings)
        except SQLSecurityError:
            raise
        except Exception as e:
            # 校验器异常不阻断查询, 回退到轻量关键词检查
            from app.engines.sql_validator import quick_select_check
            if not quick_select_check(generated_sql):
                raise SQLSecurityError("SQL安全校验未通过，仅允许SELECT查询")

    # 7. Execute SQL if valid and datasource available
    query_data = []
    query_columns = []
    row_count = 0
    exec_error = None
    execution_time = 0

    if generated_sql and ds:
        exec_start = time.time()
        try:
            # Execute via datasource connection
            from app.engines import execute_query
            query_data, query_columns = await execute_query(ds, generated_sql)
            row_count = len(query_data)
            execution_time = int((time.time() - exec_start) * 1000)
        except ImportError:
            exec_error = "查询引擎未配置"
        except Exception as e:
            exec_error = str(e)
            execution_time = int((time.time() - exec_start) * 1000)
    elif generated_sql and not ds:
        exec_error = "请先选择数据源"

    # 8. Save assistant message
    chart_config = None
    if query_data and query_columns:
        # Auto-generate chart suggestion
        chart_config = _suggest_chart(data.question, query_columns, query_data)

    assistant_msg = ConversationMessage(
        conversation_id=conv.id,
        role="assistant",
        content=llm_answer or "查询完成",
        sql_generated=generated_sql,
        sql_executed=generated_sql if not exec_error else None,
        query_result={"columns": query_columns, "data": query_data[:100]} if query_data else None,
        chart_config=chart_config,
        execution_time=execution_time,
        row_count=row_count,
        status="success" if not exec_error else "error",
        error_message=exec_error,
    )
    db.add(assistant_msg)

    # Update conversation
    conv.message_count += 2
    conv.last_active_at = datetime.utcnow()

    # 9. Log query
    query_log = QueryLog(
        user_id=user.id if user else None,
        conversation_id=conv.id,
        datasource_id=ds.id if ds else None,
        user_question=data.question,
        generated_sql=generated_sql,
        execution_time=execution_time,
        row_count=row_count,
        status="success" if not exec_error else "error",
        error_detail=exec_error,
    )
    db.add(query_log)

    await db.flush()

    total_time = int((time.time() - start_time) * 1000)

    return ApiResponse(data={
        "query_id": str(assistant_msg.id),
        "conversation_id": str(conv.id),
        "answer": llm_answer,
        "sql": generated_sql,
        "data": query_data[:100],
        "columns": query_columns,
        "chart": chart_config,
        "row_count": row_count,
        "execution_time": execution_time,
        "total_time": total_time,
        "error": exec_error,
        "warnings": sql_warnings,
        "llm_degraded": llm_degraded,
    })


@router.post("/execute", response_model=ApiResponse)
async def execute_sql(
    data: QueryExecuteRequest,
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """直接执行SQL查询（只读）"""
    try:
        from app.engines.sql_validator import validate_and_fix
        data.sql, _ = await validate_and_fix(
            data.sql, max_rows=settings.max_query_rows
        )
    except SQLSecurityError:
        raise
    except Exception:
        if not validate_sql_safety(data.sql):
            raise SQLSecurityError("仅允许SELECT查询")

    result = await db.execute(
        select(Datasource).where(Datasource.id == data.datasource_id)
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")

    try:
        from app.engines import execute_query
        query_data, query_columns = await execute_query(ds, data.sql)
        return ApiResponse(data={
            "columns": query_columns,
            "data": query_data[:1000],
            "row_count": len(query_data),
        })
    except ImportError:
        raise DatasourceConnectionError("查询引擎未配置")
    except Exception as e:
        raise SQLExecutionError(str(e))


@router.get("/{query_id}/export")
async def export_query_result(
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """导出查询结果为 CSV 文件"""
    result = await db.execute(
        select(ConversationMessage).where(ConversationMessage.id == query_id)
    )
    msg = result.scalar_one_or_none()
    if not msg or not msg.query_result:
        raise NotFoundException("查询结果不存在")

    columns = msg.query_result.get("columns", [])
    rows = msg.query_result.get("data", [])
    col_names = [c["name"] for c in columns]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(col_names)
    for row in rows:
        writer.writerow([row.get(c, "") for c in col_names])
    buf.seek(0)

    filename = f"query_{str(query_id)[:8]}.csv"
    return StreamingResponse(
        iter(["\ufeff", buf.getvalue()]),  # BOM 保证 Excel 中文不乱码
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{query_id}/feedback", response_model=ApiResponse)
async def submit_feedback(
    query_id: uuid.UUID,
    data: QueryFeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """提交查询反馈（点赞/点踩）"""
    result = await db.execute(
        select(ConversationMessage).where(ConversationMessage.id == query_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise NotFoundException("查询记录不存在")

    msg.feedback = data.feedback
    return ApiResponse(message="反馈已提交")


def _suggest_chart(question: str, columns: list, data: list) -> dict:
    """Auto-suggest chart type based on question and data shape."""
    q = question.lower()
    num_cols = [c for c in columns if c.get("type", "").lower() in ("int", "integer", "bigint", "float", "decimal", "numeric", "double", "number")]
    str_cols = [c for c in columns if c.get("type", "").lower() in ("varchar", "text", "char", "string", "name")]

    # Trend keywords
    if any(kw in q for kw in ["趋势", "变化", "走势", "月度", "季度", "年度", "daily", "monthly"]):
        return {"type": "line", "xField": columns[0]["name"] if columns else "", "yField": num_cols[0]["name"] if num_cols else ""}

    # Ranking
    if any(kw in q for kw in ["排名", "TOP", "top", "排行", "最多", "最高", "最低"]):
        return {"type": "bar", "xField": str_cols[0]["name"] if str_cols else "", "yField": num_cols[0]["name"] if num_cols else ""}

    # Distribution / proportion
    if any(kw in q for kw in ["占比", "比例", "分布", "构成", "份额"]):
        return {"type": "pie", "angleField": num_cols[0]["name"] if num_cols else "", "colorField": str_cols[0]["name"] if str_cols else ""}

    # Comparison
    if any(kw in q for kw in ["对比", "比较", "vs", "各", "分别"]):
        return {"type": "bar", "xField": str_cols[0]["name"] if str_cols else "", "yField": num_cols[0]["name"] if num_cols else ""}

    # Default: table
    return {"type": "table"}
