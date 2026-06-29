import uuid
from typing import Optional
from sqlalchemy import String, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntegrationSettings(Base):
    __tablename__ = "integration_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    login: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
