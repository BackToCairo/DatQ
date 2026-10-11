"""Pydantic schemas for API request/response validation."""
import uuid
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, EmailStr


# ========== Common ==========

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int


# ========== Auth ==========

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ========== User ==========

class UserBase(BaseModel):
    username: str
    email: str
    display_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: uuid.UUID
    status: str
    avatar_url: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    roles: List[Dict] = []

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None


# ========== Datasource ==========

class DatasourceBase(BaseModel):
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str


class DatasourceCreate(DatasourceBase):
    password: str
    pool_size: int = 5
    pool_timeout: int = 30
    extra_params: Dict[str, Any] = {}


class DatasourceResponse(DatasourceBase):
    id: uuid.UUID
    status: str
    pool_size: int
    pool_timeout: int
    last_sync_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    pool_size: Optional[int] = None
    pool_timeout: Optional[int] = None
    status: Optional[str] = None


class TableMetadataResponse(BaseModel):
    id: uuid.UUID
    table_name: str
    table_comment: Optional[str] = None
    row_count: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ColumnMetadataResponse(BaseModel):
    id: uuid.UUID
    column_name: str
    column_type: str
    column_comment: Optional[str] = None
    is_nullable: bool = True
    is_primary_key: bool = False

    class Config:
        from_attributes = True


# ========== Query ==========

class QueryAskRequest(BaseModel):
    question: str
    conversation_id: Optional[uuid.UUID] = None
    datasource_id: Optional[uuid.UUID] = None


class QueryResultResponse(BaseModel):
    query_id: uuid.UUID
    conversation_id: uuid.UUID
    sql: str
    data: List[Dict[str, Any]]
    columns: List[Dict[str, str]]
    chart: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}


class QueryExecuteRequest(BaseModel):
    sql: str
    datasource_id: uuid.UUID


class QueryFeedbackRequest(BaseModel):
    feedback: str  # good/bad


# ========== Conversation ==========

class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    status: str
    message_count: int
    last_active_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sql_generated: Optional[str] = None
    sql_executed: Optional[str] = None
    query_result: Optional[Dict] = None
    chart_config: Optional[Dict] = None
    execution_time: Optional[int] = None
    row_count: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    feedback: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse] = []


# ========== Knowledge ==========

class KnowledgeDocCreate(BaseModel):
    title: str
    doc_type: str
    content: str
    datasource_id: Optional[uuid.UUID] = None


class KnowledgeDocResponse(BaseModel):
    id: uuid.UUID
    title: str
    doc_type: str
    chunk_count: int
    datasource_id: Optional[uuid.UUID] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SqlExampleCreate(BaseModel):
    question: str
    sql_content: str
    description: Optional[str] = None
    datasource_id: Optional[uuid.UUID] = None
    tags: List[str] = []


class SqlExampleResponse(BaseModel):
    id: uuid.UUID
    question: str
    sql_content: str
    description: Optional[str] = None
    use_count: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RetrieveTestRequest(BaseModel):
    query: str
    top_k: int = 5


class RetrieveTestResponse(BaseModel):
    results: List[Dict[str, Any]]


# ========== Semantic ==========

class SemanticModelCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    datasource_id: uuid.UUID
    base_table: str


class SemanticModelResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: Optional[str] = None
    datasource_id: uuid.UUID
    base_table: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MetricCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    expression: str
    data_type: str
    dimensions: List[str] = []
    synonyms: List[str] = []
    tags: List[str] = []


class MetricResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    expression: str
    data_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DimensionCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    column_name: str
    data_type: str
    hierarchy_level: int = 0
    synonyms: List[str] = []


class DimensionResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    column_name: str
    data_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Dashboard ==========

class DashboardCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = False


class DashboardResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_public: bool
    owner_id: uuid.UUID
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class WidgetCreate(BaseModel):
    widget_type: str
    title: Optional[str] = None
    config: Dict[str, Any]
    position_x: int = 0
    position_y: int = 0
    width: int = 6
    height: int = 4


class WidgetResponse(BaseModel):
    id: uuid.UUID
    widget_type: str
    title: Optional[str] = None
    config: Dict[str, Any]
    position_x: int
    position_y: int
    width: int
    height: int

    class Config:
        from_attributes = True


# ========== Admin ==========

class RoleCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AssignRolesRequest(BaseModel):
    role_ids: List[uuid.UUID]


class SystemOverviewResponse(BaseModel):
    total_users: int
    total_datasources: int
    total_conversations: int
    total_queries_today: int
    active_datasources: int
