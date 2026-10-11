"""Audit log models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    conversation_id = Column(UUID(as_uuid=True))
    user_question = Column(Text, nullable=False)
    generated_sql = Column(Text)
    executed_sql = Column(Text)
    datasource_id = Column(UUID(as_uuid=True))
    status = Column(String(16), nullable=False)
    execution_time = Column(Integer)
    row_count = Column(Integer)
    llm_model = Column(String(64))
    token_used = Column(Integer)
    error_detail = Column(Text)
    ip_address = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String(64), nullable=False)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(128))
    detail = Column(JSONB)
    ip_address = Column(String(64))
    user_agent = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
