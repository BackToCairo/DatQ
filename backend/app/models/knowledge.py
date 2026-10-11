"""Knowledge base models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(256), nullable=False)
    doc_type = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    source_file = Column(String(512))
    chunk_count = Column(Integer, default=0)
    datasource_id = Column(UUID(as_uuid=True), ForeignKey("datasources.id"))
    status = Column(String(16), default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    chunks = relationship("KnowledgeChunk", back_populates="doc", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_docs.id", ondelete="CASCADE"))
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer)
    vector_id = Column(String(128))
    metadata_ = Column("metadata", JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    doc = relationship("KnowledgeDoc", back_populates="chunks")


class SqlExample(Base):
    __tablename__ = "sql_examples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(Text, nullable=False)
    sql_content = Column(Text, nullable=False)
    description = Column(Text)
    datasource_id = Column(UUID(as_uuid=True), ForeignKey("datasources.id"))
    tags = Column(ARRAY(String))
    use_count = Column(Integer, default=0)
    success_rate = Column(Integer)
    status = Column(String(16), default="active")
    vector_id = Column(String(128))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
