"""管理员统一的大模型配置，密钥仅以 Fernet 密文存储。"""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_system_settings_singleton"),)

    id = Column(Integer, primary_key=True, default=1)
    base_url = Column(String(2048), nullable=False, default="")
    model = Column(String(128), nullable=False)
    api_key_enc = Column(LargeBinary, nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
