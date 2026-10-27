"""Admin API routes: 用户管理/角色管理/审计日志/统计。"""
import uuid
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User, Role, UserRole, Permission, RolePermission
from app.models.log import QueryLog, OperationLog
from app.models.datasource import Datasource
from app.models.conversation import Conversation
from app.schemas.schemas import (
    UserCreate, UserUpdate, RoleCreate, RoleResponse,
    AssignRolesRequest, ApiResponse, LlmSettingsRequest,
)
from app.services import llm_config_service
from app.core.deps import require_admin
from app.core.exceptions import NotFoundException, AlreadyExistsException, ValidationException
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["系统管理"])


async def _log_operation(db: AsyncSession, user_id, action: str,
                         resource_type: str, resource_id: str = None, detail=None):
    db.add(OperationLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        detail=detail,
    ))


async def _get_user_with_roles(db: AsyncSession, user_id) -> Optional[User]:
    """按ID查用户并预加载 roles(异步会话禁止懒加载)。"""
    return (await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )).scalar_one_or_none()


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "phone": user.phone,
        "status": user.status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "roles": [{"id": str(r.id), "name": r.name, "display_name": r.display_name}
                  for r in (user.roles or [])],
    }


# ========== 管理员统一大模型配置 ==========

@router.get("/settings/llm", response_model=ApiResponse)
async def get_llm_settings(
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    return ApiResponse(data=await llm_config_service.describe_config(db))


@router.put("/settings/llm", response_model=ApiResponse)
async def update_llm_settings(
    data: LlmSettingsRequest,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    public = await llm_config_service.save_config(db, data, admin.id)
    # 不将请求对象、明文或密文密钥写入审计日志。
    await _log_operation(db, admin.id, "update", "llm_settings", "1", {
        "has_api_key": public["has_api_key"], "clear_api_key": data.clear_api_key,
    })
    await db.flush()
    return ApiResponse(message="配置已保存，下一次模型调用生效", data=public)


@router.post("/settings/llm/test", response_model=ApiResponse)
async def test_llm_settings(
    data: LlmSettingsRequest,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    result = await llm_config_service.probe_config(db, data)
    return ApiResponse(code=0 if result["success"] else 1, message=result["message"], data=result)


# ========== 用户管理 ==========

@router.get("/users", response_model=ApiResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """用户列表(分页/搜索)"""
    query = select(User).options(selectinload(User.roles))
    count_query = select(func.count(User.id))
    if search:
        like = f"%{search}%"
        cond = User.username.ilike(like) | User.email.ilike(like) | User.display_name.ilike(like)
        query = query.where(cond)
        count_query = count_query.where(cond)
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().unique().all()
    return ApiResponse(data={"items": [_serialize_user(u) for u in users],
                             "total": total, "page": page, "page_size": page_size})


@router.post("/users", response_model=ApiResponse)
async def create_user(
    data: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """管理员创建用户"""
    exists = (await db.execute(
        select(User).where((User.username == data.username) | (User.email == data.email))
    )).scalar_one_or_none()
    if exists:
        raise AlreadyExistsException("用户名或邮箱已存在")

    user = User(
        username=data.username, email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name, phone=data.phone,
    )
    db.add(user)
    await _log_operation(db, admin.id, "create", "user", detail={"username": data.username})
    await db.flush()
    user = await _get_user_with_roles(db, user.id)
    return ApiResponse(data=_serialize_user(user))


@router.put("/users/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新用户信息"""
    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    await _log_operation(db, admin.id, "update", "user", user.id, update_data)
    await db.flush()
    await db.refresh(user)
    return ApiResponse(data=_serialize_user(user))


@router.patch("/users/{user_id}/status", response_model=ApiResponse)
async def update_user_status(
    user_id: uuid.UUID,
    status: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用用户"""
    if status not in ("active", "disabled"):
        raise ValidationException("status 仅支持 active/disabled")
    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    if user.id == admin.id and status == "disabled":
        raise ValidationException("不能禁用自己")
    user.status = status
    await _log_operation(db, admin.id, "update_status", "user", user.id, {"status": status})
    await db.flush()
    return ApiResponse(data=_serialize_user(user))


@router.put("/users/{user_id}/roles", response_model=ApiResponse)
async def assign_roles(
    user_id: uuid.UUID,
    data: AssignRolesRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """分配用户角色(全量覆盖)"""
    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("用户不存在")

    roles = []
    for rid in data.role_ids:
        role = (await db.execute(select(Role).where(Role.id == rid))).scalar_one_or_none()
        if not role:
            raise NotFoundException(f"角色 {rid} 不存在")
        roles.append(role)

    # 全量覆盖 user_roles
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(UserRole).where(UserRole.user_id == user.id))
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))

    await _log_operation(db, admin.id, "assign_roles", "user", user.id,
                         {"roles": [r.name for r in roles]})
    await db.flush()
    user = await _get_user_with_roles(db, user.id)
    return ApiResponse(data=_serialize_user(user))


# ========== 角色管理 ==========

@router.get("/roles", response_model=ApiResponse)
async def list_roles(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """角色列表"""
    roles = (await db.execute(select(Role).order_by(Role.created_at))).scalars().all()
    items = [RoleResponse.model_validate(r).model_dump(mode="json") for r in roles]
    return ApiResponse(data=items)


@router.post("/roles", response_model=ApiResponse)
async def create_role(
    data: RoleCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建角色"""
    exists = (await db.execute(select(Role).where(Role.name == data.name))).scalar_one_or_none()
    if exists:
        raise AlreadyExistsException(f"角色 {data.name} 已存在")
    role = Role(name=data.name, display_name=data.display_name,
                description=data.description, is_system=False)
    db.add(role)
    await _log_operation(db, admin.id, "create", "role", detail={"name": data.name})
    await db.flush()
    await db.refresh(role)
    return ApiResponse(data=RoleResponse.model_validate(role).model_dump(mode="json"))


# ========== 审计日志 ==========

@router.get("/logs/queries", response_model=ApiResponse)
async def list_query_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    datasource_id: Optional[uuid.UUID] = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询审计日志"""
    query = select(QueryLog)
    count_query = select(func.count(QueryLog.id))
    conds = []
    if status:
        conds.append(QueryLog.status == status)
    if user_id:
        conds.append(QueryLog.user_id == user_id)
    if datasource_id:
        conds.append(QueryLog.datasource_id == datasource_id)
    for cond in conds:
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await db.execute(count_query)).scalar() or 0
    logs = (await db.execute(
        query.order_by(QueryLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    items = [{
        "id": str(l.id),
        "user_id": str(l.user_id) if l.user_id else None,
        "question": l.user_question,
        "sql": l.generated_sql,
        "datasource_id": str(l.datasource_id) if l.datasource_id else None,
        "status": l.status,
        "execution_time": l.execution_time,
        "row_count": l.row_count,
        "error": l.error_detail,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    } for l in logs]
    return ApiResponse(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/logs/operations", response_model=ApiResponse)
async def list_operation_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """操作审计日志"""
    query = select(OperationLog)
    count_query = select(func.count(OperationLog.id))
    if action:
        query = query.where(OperationLog.action == action)
        count_query = count_query.where(OperationLog.action == action)

    total = (await db.execute(count_query)).scalar() or 0
    logs = (await db.execute(
        query.order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    # 批量补用户名
    user_ids = {l.user_id for l in logs if l.user_id}
    users_map = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_map = {u.id: u.username for u in users}

    items = [{
        "id": str(l.id),
        "username": users_map.get(l.user_id),
        "action": l.action,
        "resource_type": l.resource_type,
        "resource_id": l.resource_id,
        "detail": l.detail,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    } for l in logs]
    return ApiResponse(data={"items": items, "total": total, "page": page, "page_size": page_size})


# ========== 统计 ==========

@router.get("/stats/query-trend", response_model=ApiResponse)
async def query_trend(
    days: int = Query(14, ge=1, le=90),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """近N天查询趋势(按天统计总量/成功量)"""
    since = datetime.utcnow() - timedelta(days=days)
    rows = (await db.execute(
        select(
            func.date(QueryLog.created_at).label("day"),
            func.count(QueryLog.id).label("total"),
            func.sum(case((QueryLog.status == "success", 1), else_=0)).label("success"),
        )
        .where(QueryLog.created_at >= since)
        .group_by(func.date(QueryLog.created_at))
        .order_by(func.date(QueryLog.created_at))
    )).all()
    items = [{"date": str(r.day), "total": int(r.total), "success": int(r.success or 0)}
             for r in rows]
    return ApiResponse(data=items)


@router.get("/stats/datasource-distribution", response_model=ApiResponse)
async def datasource_distribution(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """数据源查询量分布"""
    rows = (await db.execute(
        select(Datasource.name, Datasource.db_type, func.count(QueryLog.id).label("cnt"))
        .join(QueryLog, QueryLog.datasource_id == Datasource.id, isouter=True)
        .group_by(Datasource.id, Datasource.name, Datasource.db_type)
        .order_by(Datasource.name)
    )).all()
    items = [{"name": r.name, "db_type": r.db_type, "query_count": int(r.cnt or 0)}
             for r in rows]
    return ApiResponse(data=items)
