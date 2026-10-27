"""API v1 routes package."""
from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.datasource import router as datasource_router
from app.api.v1.conversation import router as conversation_router
from app.api.v1.query import router as query_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.semantic import router as semantic_router
from app.api.v1.admin import router as admin_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(datasource_router)
api_v1_router.include_router(conversation_router)
api_v1_router.include_router(query_router)
api_v1_router.include_router(knowledge_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(semantic_router)
api_v1_router.include_router(admin_router)
