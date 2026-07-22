import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Text, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TeacherAppointment(Base):
    __tablename__ = "teacher_appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_confirm: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_come: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    teacher: Mapped["User"] = relationship("User", foreign_keys=[teacher_id])
