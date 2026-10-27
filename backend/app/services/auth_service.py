"""Authentication service."""
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, Role
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
from app.core.exceptions import UnauthorizedException, NotFoundException, AlreadyExistsException
from app.schemas.schemas import UserCreate, LoginRequest


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserCreate) -> User:
        # Check if user exists
        result = await self.db.execute(select(User).where(User.username == data.username))
        if result.scalar_one_or_none():
            raise AlreadyExistsException(f"用户名 {data.username} 已存在")

        result = await self.db.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise AlreadyExistsException(f"邮箱 {data.email} 已存在")

        # Create user
        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            display_name=data.display_name,
            phone=data.phone,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, data: LoginRequest) -> dict:
        # Find user
        result = await self.db.execute(select(User).where(User.username == data.username))
        user = result.scalar_one_or_none()
        if not user:
            raise UnauthorizedException("用户名或密码错误")

        if user.status != "active":
            raise UnauthorizedException("账号已被禁用")

        if not verify_password(data.password, user.password_hash):
            raise UnauthorizedException("用户名或密码错误")

        # Update last login
        user.last_login_at = datetime.utcnow()
        await self.db.flush()

        # Generate tokens
        token_data = {"sub": str(user.id), "username": user.username}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 7200,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "status": user.status,
            }
        }

    async def get_current_user(self, token: str) -> User:
        payload = decode_token(token)
        if not payload:
            raise UnauthorizedException("无效的Token")

        if payload.get("type") != "access":
            raise UnauthorizedException("Token类型错误")

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException("无效的Token")

        # 预加载 roles, 避免异步会话中懒加载触发 MissingGreenlet
        result = await self.db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UnauthorizedException("用户不存在")

        if user.status != "active":
            raise UnauthorizedException("账号已被禁用")

        return user

    async def refresh_token(self, refresh_token: str) -> dict:
        payload = decode_token(refresh_token)
        if not payload:
            raise UnauthorizedException("无效的Refresh Token")

        if payload.get("type") != "refresh":
            raise UnauthorizedException("Token类型错误")

        user_id = payload.get("sub")
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise UnauthorizedException("用户不存在")

        token_data = {"sub": str(user.id), "username": user.username}
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_in": 7200,
        }
