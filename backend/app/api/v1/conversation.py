"""Conversation API routes."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.conversation import Conversation, ConversationMessage
from app.schemas.schemas import (
    ConversationCreate, ConversationResponse, ConversationDetailResponse,
    MessageResponse, ApiResponse
)
from app.core.exceptions import NotFoundException
from app.services.auth_service import AuthService

router = APIRouter(prefix="/conversations", tags=["对话"])


@router.get("", response_model=ApiResponse)
async def list_conversations(
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的会话列表"""
    if not authorization:
        return ApiResponse(data=[])

    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    auth_service = AuthService(db)
    try:
        user = await auth_service.get_current_user(token)
    except:
        return ApiResponse(data=[])

    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.status == "active")
        .order_by(Conversation.last_active_at.desc())
    )
    conversations = result.scalars().all()
    items = [ConversationResponse.model_validate(c).model_dump() for c in conversations]
    return ApiResponse(data=items)


@router.post("", response_model=ApiResponse)
async def create_conversation(
    data: ConversationCreate,
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """创建新会话"""
    token = authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization
    auth_service = AuthService(db)
    user = await auth_service.get_current_user(token)

    conv = Conversation(
        user_id=user.id,
        title=data.title or "新对话",
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return ApiResponse(data=ConversationResponse.model_validate(conv).model_dump())


@router.get("/{conv_id}", response_model=ApiResponse)
async def get_conversation(conv_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取会话详情及消息历史"""
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundException("会话不存在")

    # Get messages
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv_id)
        .order_by(ConversationMessage.created_at)
    )
    messages = result.scalars().all()

    conv_data = ConversationDetailResponse.model_validate(conv).model_dump()
    conv_data["messages"] = [MessageResponse.model_validate(m).model_dump() for m in messages]
    return ApiResponse(data=conv_data)


@router.delete("/{conv_id}", response_model=ApiResponse)
async def delete_conversation(conv_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除会话（软删除）"""
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundException("会话不存在")

    conv.status = "deleted"
    conv.updated_at = datetime.utcnow()
    return ApiResponse(message="删除成功")


@router.post("/{conv_id}/messages", response_model=ApiResponse)
async def add_message(
    conv_id: uuid.UUID,
    role: str,
    content: str,
    sql_generated: str = None,
    sql_executed: str = None,
    query_result: dict = None,
    chart_config: dict = None,
    execution_time: int = None,
    row_count: int = None,
    status: str = "success",
    error_message: str = None,
    db: AsyncSession = Depends(get_db)
):
    """添加消息到会话"""
    result = await db.execute(select(Conversation).where(Conversation.id == conv_id))
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundException("会话不存在")

    msg = ConversationMessage(
        conversation_id=conv_id,
        role=role,
        content=content,
        sql_generated=sql_generated,
        sql_executed=sql_executed,
        query_result=query_result,
        chart_config=chart_config,
        execution_time=execution_time,
        row_count=row_count,
        status=status,
        error_message=error_message,
    )
    db.add(msg)

    # Update conversation
    conv.message_count += 1
    conv.last_active_at = datetime.utcnow()

    await db.flush()
    await db.refresh(msg)
    return ApiResponse(data=MessageResponse.model_validate(msg).model_dump())
