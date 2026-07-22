"""Yordamchi ustoz: kurslarga biriktirish, ish jadvali, dam olish kunlari."""
import uuid
from datetime import date as DateType, time as TimeType

from sqlalchemy import String, Text, Date, Time, Boolean, SmallInteger, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssistantCourse(Base):
    """Yordamchi ustoz qaysi kurs(lar)ga biriktirilgan."""
    __tablename__ = "assistant_courses"
    __table_args__ = (UniqueConstraint("assistant_id", "course_id", name="assistant_courses_uniq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), index=True)


class AssistantAvailability(Base):
    """Haftalik ish jadvali: qaysi kuni, qaysi vaqtdan qaysi vaqtgacha (+ tushlik)."""
    __tablename__ = "assistant_availability"
    __table_args__ = (UniqueConstraint("assistant_id", "weekday", name="assistant_availability_uniq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)          # 0=Dushanba ... 6=Yakshanba
    start_time: Mapped[TimeType] = mapped_column(Time)
    end_time: Mapped[TimeType] = mapped_column(Time)
    break_start: Mapped[TimeType | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[TimeType | None] = mapped_column(Time, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AssistantDayOff(Base):
    """Dam olish kuni — o'sha kuni bron qilib bo'lmaydi."""
    __tablename__ = "assistant_day_off"
    __table_args__ = (UniqueConstraint("assistant_id", "date", name="assistant_day_off_uniq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[DateType] = mapped_column(Date, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
