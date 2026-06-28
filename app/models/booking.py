import uuid
from datetime import date
from sqlalchemy import String, Text, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(300))
    date: Mapped[date] = mapped_column(Date)
    time_slot: Mapped[str] = mapped_column(String(10))
    status: Mapped[BookingStatus] = mapped_column(SAEnum(BookingStatus), default=BookingStatus.pending)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    teacher: Mapped["User"] = relationship("User", back_populates="bookings_as_teacher", foreign_keys=[teacher_id])
    student: Mapped["User"] = relationship("User", back_populates="bookings_as_student", foreign_keys=[student_id])
