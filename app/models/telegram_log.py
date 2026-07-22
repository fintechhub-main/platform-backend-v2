import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, Text, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TelegramLog(Base):
    __tablename__ = "telegram_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), default="attendance")  # attendance | ...
    log_date: Mapped[date | None] = mapped_column(Date, nullable=True)   # qaysi kun davomati
    status: Mapped[str] = mapped_column(String(10))                      # sent | failed
    chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Telegramning sendMessage javobidan olingan xabar ID — keyinchalik
    # editMessageText bilan shu xabarni yangilash uchun kerak.
    message_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
