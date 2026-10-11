"""Semantic layer models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base


class SemanticModel(Base):
    __tablename__ = "semantic_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), nullable=False, unique=True)
    display_name = Column(String(128), nullable=False)
    description = Column(Text)
    datasource_id = Column(UUID(as_uuid=True), ForeignKey("datasources.id"))
    base_table = Column(String(128), nullable=False)
    status = Column(String(16), default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    metrics = relationship("Metric", back_populates="model", cascade="all, delete-orphan")
    dimensions = relationship("Dimension", back_populates="model", cascade="all, delete-orphan")


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("semantic_models.id", ondelete="CASCADE"))
    name = Column(String(128), nullable=False)
    display_name = Column(String(128), nullable=False)
    description = Column(Text)
    expression = Column(Text, nullable=False)
    data_type = Column(String(32), nullable=False)
    dimensions = Column(JSONB, default=[])
    default_filters = Column(JSONB, default={})
    synonyms = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    model = relationship("SemanticModel", back_populates="metrics")


class Dimension(Base):
    __tablename__ = "dimensions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("semantic_models.id", ondelete="CASCADE"))
    name = Column(String(128), nullable=False)
    display_name = Column(String(128), nullable=False)
    description = Column(Text)
    column_name = Column(String(128), nullable=False)
    data_type = Column(String(32), nullable=False)
    hierarchy_level = Column(Integer, default=0)
    parent_dim_id = Column(UUID(as_uuid=True), ForeignKey("dimensions.id"))
    synonyms = Column(ARRAY(String))
    status = Column(String(16), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    model = relationship("SemanticModel", back_populates="dimensions")
