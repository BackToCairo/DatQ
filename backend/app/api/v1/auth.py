"""Authentication API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.auth_service import AuthService
from app.schemas.schemas import LoginRequest, UserCreate, RefreshTokenRequest, ApiResponse
from app.core.security import decode_token
from app.core.exceptions import UnauthorizedException

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    service = AuthService(db)
    result = await service.login(data)
    return ApiResponse(data=result)


@router.post("/register", response_model=ApiResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    service = AuthService(db)
    user = await service.register(data)
    return ApiResponse(data={"id": str(user.id), "username": user.username})


@router.post("/refresh", response_model=ApiResponse)
async def refresh_token(data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """刷新Token"""
    service = AuthService(db)
    result = await service.refresh_token(data.refresh_token)
    return ApiResponse(data=result)


@router.get("/me", response_model=ApiResponse)
async def get_current_user(
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户信息"""
    if not authorization:
        raise UnauthorizedException("未提供认证信息")

    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    service = AuthService(db)
    user = await service.get_current_user(token)

    return ApiResponse(data={
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "status": user.status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    })
