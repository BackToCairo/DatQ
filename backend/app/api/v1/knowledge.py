"""Knowledge API routes - document and SQL example management."""
import uuid
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, async_session_factory
from app.models.knowledge import KnowledgeDoc, KnowledgeChunk, SqlExample
from app.schemas.schemas import (
    KnowledgeDocCreate, KnowledgeDocResponse,
    SqlExampleCreate, SqlExampleResponse,
    RetrieveTestRequest, RetrieveTestResponse,
    ApiResponse
)
from app.core.exceptions import NotFoundException
from app.services import rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["知识库"])


def _index_doc_task(doc_id: str, title: str, content: str, datasource_id: Optional[str]):
    """后台任务: 文档分块向量化入库, 并回写 chunk_count。"""
    async def _run():
        try:
            count = await rag_service.index_document(doc_id, title, content, datasource_id)
            async with async_session_factory() as session:
                result = await session.execute(
                    select(KnowledgeDoc).where(KnowledgeDoc.id == uuid.UUID(doc_id))
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.chunk_count = count
                    doc.status = "active"
                    await session.commit()
        except Exception as e:
            logger.warning("文档向量化失败: %s", e)
            try:
                async with async_session_factory() as session:
                    result = await session.execute(
                        select(KnowledgeDoc).where(KnowledgeDoc.id == uuid.UUID(doc_id))
                    )
                    doc = result.scalar_one_or_none()
                    if doc:
                        doc.status = "error"
                        await session.commit()
            except Exception:
                pass
    import asyncio
    asyncio.get_running_loop().create_task(_run())


# ========== 文档管理 ==========

@router.get("/docs", response_model=ApiResponse)
async def list_docs(
    datasource_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取知识文档列表"""
    query = select(KnowledgeDoc).order_by(KnowledgeDoc.created_at.desc())
    if datasource_id:
        query = query.where(KnowledgeDoc.datasource_id == datasource_id)
    result = await db.execute(query)
    docs = result.scalars().all()
    items = [KnowledgeDocResponse.model_validate(d).model_dump() for d in docs]
    return ApiResponse(data=items)


@router.post("/docs", response_model=ApiResponse)
async def create_doc(
    data: KnowledgeDocCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建知识文档(自动后台分块向量化)"""
    doc = KnowledgeDoc(
        title=data.title,
        doc_type=data.doc_type,
        content=data.content,
        datasource_id=data.datasource_id,
        chunk_count=0,
        status="processing",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    _index_doc_task(str(doc.id), doc.title, doc.content,
                    str(data.datasource_id) if data.datasource_id else None)

    return ApiResponse(data=KnowledgeDocResponse.model_validate(doc).model_dump())


@router.post("/docs/upload", response_model=ApiResponse)
async def upload_doc(
    file: UploadFile = File(...),
    title: str = Form(None),
    doc_type: str = Form("file"),
    datasource_id: Optional[uuid.UUID] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """上传知识文档文件"""
    content = await file.read()
    text = content.decode("utf-8-sig")

    doc = KnowledgeDoc(
        title=title or file.filename or "未命名文档",
        doc_type=doc_type,
        content=text,
        datasource_id=datasource_id,
        source_file=file.filename,
        chunk_count=0,
        status="processing",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # 后台分块向量化, 完成后回写 chunk_count 与状态
    _index_doc_task(str(doc.id), doc.title, text,
                    str(datasource_id) if datasource_id else None)

    return ApiResponse(
        data=KnowledgeDocResponse.model_validate(doc).model_dump(),
        message="文档上传成功，正在后台进行分块向量化"
    )


@router.delete("/docs/{doc_id}", response_model=ApiResponse)
async def delete_doc(doc_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除知识文档(同时清理向量索引)"""
    result = await db.execute(select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("文档不存在")
    await db.delete(doc)
    try:
        await rag_service.delete_doc_vectors(str(doc_id))
    except Exception:
        pass
    return ApiResponse(message="删除成功")


# ========== SQL示例管理 ==========

@router.get("/sql-examples", response_model=ApiResponse)
async def list_sql_examples(
    datasource_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取SQL示例列表"""
    query = select(SqlExample).order_by(SqlExample.created_at.desc())
    if datasource_id:
        query = query.where(SqlExample.datasource_id == datasource_id)
    result = await db.execute(query)
    examples = result.scalars().all()
    items = [SqlExampleResponse.model_validate(e).model_dump() for e in examples]
    return ApiResponse(data=items)


@router.post("/sql-examples", response_model=ApiResponse)
async def create_sql_example(
    data: SqlExampleCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建SQL示例"""
    example = SqlExample(
        question=data.question,
        sql_content=data.sql_content,
        description=data.description,
        datasource_id=data.datasource_id,
        tags=data.tags,
        use_count=0,
        status="active",
    )
    db.add(example)
    await db.flush()
    await db.refresh(example)

    try:
        await rag_service.index_sql_example(
            str(example.id), data.question, data.sql_content,
            str(data.datasource_id) if data.datasource_id else None,
        )
    except Exception:
        pass

    return ApiResponse(data=SqlExampleResponse.model_validate(example).model_dump())


@router.put("/sql-examples/{example_id}", response_model=ApiResponse)
async def update_sql_example(
    example_id: uuid.UUID,
    data: SqlExampleCreate,
    db: AsyncSession = Depends(get_db)
):
    """更新SQL示例"""
    result = await db.execute(select(SqlExample).where(SqlExample.id == example_id))
    example = result.scalar_one_or_none()
    if not example:
        raise NotFoundException("SQL示例不存在")

    example.question = data.question
    example.sql_content = data.sql_content
    example.description = data.description
    example.datasource_id = data.datasource_id
    example.tags = data.tags
    await db.flush()
    await db.refresh(example)

    try:
        await rag_service.index_sql_example(
            str(example.id), data.question, data.sql_content,
            str(data.datasource_id) if data.datasource_id else None,
        )
    except Exception:
        pass

    return ApiResponse(data=SqlExampleResponse.model_validate(example).model_dump())


@router.delete("/sql-examples/{example_id}", response_model=ApiResponse)
async def delete_sql_example(example_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除SQL示例"""
    result = await db.execute(select(SqlExample).where(SqlExample.id == example_id))
    example = result.scalar_one_or_none()
    if not example:
        raise NotFoundException("SQL示例不存在")
    await db.delete(example)
    try:
        await rag_service.delete_sql_example_vectors(str(example_id))
    except Exception:
        pass
    return ApiResponse(message="删除成功")


# ========== 检索测试 ==========

@router.post("/retrieve-test", response_model=ApiResponse)
async def retrieve_test(
    data: RetrieveTestRequest,
    db: AsyncSession = Depends(get_db)
):
    """检索测试 - 真实向量检索(ChromaDB), 异常时回退DB关键词匹配"""
    results = []
    try:
        rag_res = await rag_service.retrieve(data.query, top_k=data.top_k)
        type_map = {"ddl_schemas": "ddl", "knowledge_docs": "document", "sql_examples": "sql_example"}
        for col, rtype in type_map.items():
            for item in rag_res.get(col, []):
                results.append({
                    "id": item["id"],
                    "type": rtype,
                    "content": item["content"],
                    "question": (item.get("metadata") or {}).get("question", ""),
                    "score": item["score"],
                })
        results.sort(key=lambda x: x["score"], reverse=True)
    except Exception:
        pass

    if not results:
        # 兜底: DB关键词匹配(SQL示例)
        db_examples = (await db.execute(
            select(SqlExample).where(SqlExample.status == "active").limit(50)
        )).scalars().all()
        for ex in db_examples:
            score = 0.5
            q_words = set(data.query.lower())
            e_words = set(ex.question.lower())
            overlap = q_words & e_words
            if overlap:
                score = min(0.95, 0.5 + len(overlap) / max(1, len(q_words | e_words)))
            results.append({
                "id": str(ex.id),
                "type": "sql_example",
                "content": f"问题: {ex.question}\nSQL:\n{ex.sql_content}",
                "question": ex.question,
                "score": round(score, 3),
            })
        results.sort(key=lambda x: x["score"], reverse=True)

    return ApiResponse(data={"results": results[:data.top_k]})
