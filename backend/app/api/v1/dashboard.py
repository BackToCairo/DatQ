"""Dashboard API routes - dashboard and widget management."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.dashboard import Dashboard, DashboardWidget
from app.models.datasource import Datasource
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.schemas import (
    DashboardCreate, DashboardResponse,
    WidgetCreate, WidgetResponse,
    SystemOverviewResponse, ApiResponse
)
from app.core.exceptions import NotFoundException
from app.services.auth_service import AuthService

router = APIRouter(prefix="/dashboards", tags=["看板"])


@router.get("", response_model=ApiResponse)
async def list_dashboards(
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取看板列表"""
    result = await db.execute(
        select(Dashboard).order_by(Dashboard.created_at.desc())
    )
    dashboards = result.scalars().all()
    items = [DashboardResponse.model_validate(d).model_dump() for d in dashboards]
    return ApiResponse(data=items)


@router.post("", response_model=ApiResponse)
async def create_dashboard(
    data: DashboardCreate,
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """创建看板"""
    user_id = None
    if authorization:
        token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
        auth_service = AuthService(db)
        try:
            user = await auth_service.get_current_user(token)
            user_id = user.id
        except:
            pass

    dashboard = Dashboard(
        name=data.name,
        description=data.description,
        is_public=data.is_public,
        owner_id=user_id,
        status="active",
    )
    db.add(dashboard)
    await db.flush()
    await db.refresh(dashboard)
    return ApiResponse(data=DashboardResponse.model_validate(dashboard).model_dump())


@router.get("/{dashboard_id}", response_model=ApiResponse)
async def get_dashboard(dashboard_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取看板详情及组件"""
    result = await db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise NotFoundException("看板不存在")

    # Get widgets
    result = await db.execute(
        select(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard_id)
        .order_by(DashboardWidget.position_y, DashboardWidget.position_x)
    )
    widgets = result.scalars().all()

    data = DashboardResponse.model_validate(dashboard).model_dump()
    data["widgets"] = [WidgetResponse.model_validate(w).model_dump() for w in widgets]
    return ApiResponse(data=data)


@router.put("/{dashboard_id}", response_model=ApiResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    data: DashboardCreate,
    db: AsyncSession = Depends(get_db)
):
    """更新看板"""
    result = await db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise NotFoundException("看板不存在")

    dashboard.name = data.name
    dashboard.description = data.description
    dashboard.is_public = data.is_public
    dashboard.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(dashboard)
    return ApiResponse(data=DashboardResponse.model_validate(dashboard).model_dump())


@router.delete("/{dashboard_id}", response_model=ApiResponse)
async def delete_dashboard(dashboard_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除看板"""
    result = await db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise NotFoundException("看板不存在")
    await db.delete(dashboard)
    return ApiResponse(message="删除成功")


# ========== 组件管理 ==========

@router.post("/{dashboard_id}/widgets", response_model=ApiResponse)
async def add_widget(
    dashboard_id: uuid.UUID,
    data: WidgetCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加看板组件"""
    result = await db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))
    if not result.scalar_one_or_none():
        raise NotFoundException("看板不存在")

    widget = DashboardWidget(
        dashboard_id=dashboard_id,
        widget_type=data.widget_type,
        title=data.title,
        config=data.config,
        position_x=data.position_x,
        position_y=data.position_y,
        width=data.width,
        height=data.height,
    )
    db.add(widget)
    await db.flush()
    await db.refresh(widget)
    return ApiResponse(data=WidgetResponse.model_validate(widget).model_dump())


@router.put("/widgets/{widget_id}", response_model=ApiResponse)
async def update_widget(
    widget_id: uuid.UUID,
    data: WidgetCreate,
    db: AsyncSession = Depends(get_db)
):
    """更新组件"""
    result = await db.execute(select(DashboardWidget).where(DashboardWidget.id == widget_id))
    widget = result.scalar_one_or_none()
    if not widget:
        raise NotFoundException("组件不存在")

    widget.widget_type = data.widget_type
    widget.title = data.title
    widget.config = data.config
    widget.position_x = data.position_x
    widget.position_y = data.position_y
    widget.width = data.width
    widget.height = data.height
    await db.flush()
    await db.refresh(widget)
    return ApiResponse(data=WidgetResponse.model_validate(widget).model_dump())


@router.delete("/widgets/{widget_id}", response_model=ApiResponse)
async def delete_widget(widget_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除组件"""
    result = await db.execute(select(DashboardWidget).where(DashboardWidget.id == widget_id))
    widget = result.scalar_one_or_none()
    if not widget:
        raise NotFoundException("组件不存在")
    await db.delete(widget)
    return ApiResponse(message="删除成功")


# ========== 系统概览 ==========

@router.get("/system/overview", response_model=ApiResponse)
async def system_overview(db: AsyncSession = Depends(get_db)):
    """系统概览统计"""
    from datetime import date
    from sqlalchemy import func

    # Total users
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0

    # Total datasources
    result = await db.execute(select(func.count(Datasource.id)))
    total_datasources = result.scalar() or 0

    # Active datasources
    result = await db.execute(
        select(func.count(Datasource.id)).where(Datasource.status == "active")
    )
    active_datasources = result.scalar() or 0

    # Total conversations
    result = await db.execute(select(func.count(Conversation.id)))
    total_conversations = result.scalar() or 0

    # Queries today
    today = date.today()
    result = await db.execute(
        select(func.count(Conversation.id)).where(
            func.date(Conversation.created_at) == today
        )
    )
    total_queries_today = result.scalar() or 0

    return ApiResponse(data={
        "total_users": total_users,
        "total_datasources": total_datasources,
        "active_datasources": active_datasources,
        "total_conversations": total_conversations,
        "total_queries_today": total_queries_today,
    })
