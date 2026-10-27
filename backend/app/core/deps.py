"""FastAPI 依赖注入: 认证与权限。"""
from typing import Optional
from fastapi import Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.services.auth_service import AuthService
from app.core.exceptions import UnauthorizedException, ForbiddenException


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """强制认证: 未携带有效Token时抛401。"""
    token = _extract_token(authorization)
    if not token:
        raise UnauthorizedException()
    auth_service = AuthService(db)
    return await auth_service.get_current_user(token)


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """可选认证: 无Token或Token无效时返回None。"""
    token = _extract_token(authorization)
    if not token:
        return None
    try:
        return await AuthService(db).get_current_user(token)
    except Exception:
        return None


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """要求管理员角色。"""
    user_roles = {r.name for r in (user.roles or [])}
    if "admin" not in user_roles and "superuser" not in user_roles:
        raise ForbiddenException("需要管理员权限")
    return user
