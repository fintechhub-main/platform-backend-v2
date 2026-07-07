import uuid
from datetime import datetime, date as DateType
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, Date, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BookPresentation(Base):
    __tablename__ = "book_presentations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)
    name_of_book: Mapped[str] = mapped_column(String(1000))
    date_presentation: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    ball_of_presentation: Mapped[int] = mapped_column(Integer, default=0)
    is_presented: Mapped[bool] = mapped_column(Boolean, default=False)
    file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
    group: Mapped[Optional["Group"]] = relationship("Group", foreign_keys=[group_id])
