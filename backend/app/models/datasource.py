"""Datasource models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, LargeBinary, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class Datasource(Base):
    __tablename__ = "datasources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text)
    # mysql/postgresql/clickhouse/sqlserver/oracle/doris/starrocks/redshift/kingbase
    db_type = Column(String(32), nullable=False)
    host = Column(String(256), nullable=False)
    port = Column(Integer, nullable=False)
    database_name = Column(String(128), nullable=False, default="")
    db_schema = Column(String(128))  # schema/owner, 部分数据库必填
    username = Column(String(128), nullable=False, default="")
    password_enc = Column(LargeBinary, nullable=False)
    connect_mode = Column(String(32), default="service_name")  # Oracle: service_name/sid
    ssl = Column(Boolean, default=False)
    extra_jdbc = Column(Text)  # 附加连接参数 k1=v1&k2=v2
    low_version = Column(Boolean, default=False)  # SQL Server 低版本兼容
    timeout = Column(Integer, default=30)  # 连接/查询超时(秒)
    extra_params = Column(JSONB, default={})
    status = Column(String(16), default="inactive")  # active/inactive/error
    pool_size = Column(Integer, default=5)
    pool_timeout = Column(Integer, default=30)
    last_sync_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tables = relationship("TableMetadata", back_populates="datasource", cascade="all, delete-orphan")


class TableMetadata(Base):
    __tablename__ = "table_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    datasource_id = Column(UUID(as_uuid=True), ForeignKey("datasources.id", ondelete="CASCADE"))
    table_name = Column(String(128), nullable=False)
    table_comment = Column(Text)
    row_count = Column(Integer)
    size_bytes = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    datasource = relationship("Datasource", back_populates="tables")
    columns = relationship("ColumnMetadata", back_populates="table", cascade="all, delete-orphan")


class ColumnMetadata(Base):
    __tablename__ = "column_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id = Column(UUID(as_uuid=True), ForeignKey("table_metadata.id", ondelete="CASCADE"))
    column_name = Column(String(128), nullable=False)
    column_type = Column(String(64), nullable=False)
    column_comment = Column(Text)
    is_nullable = Column(Integer, default=1)
    is_primary_key = Column(Integer, default=0)
    default_value = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    table = relationship("TableMetadata", back_populates="columns")
