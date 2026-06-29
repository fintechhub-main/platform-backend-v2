import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from app.database import Base


class TelegramSource(Base):
    __tablename__ = "telegram_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_url: Mapped[str] = mapped_column(String(200))
    channel_username: Mapped[str] = mapped_column(String(100))
    last_message_id: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    vacancies_found: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
