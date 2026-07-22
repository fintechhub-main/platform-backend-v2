import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, ForeignKey, Date, DateTime, Enum as SAEnum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class GroupStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    planned = "planned"
    stopped = "stopped"


class GroupStudent(Base):
    __tablename__ = "group_students"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False)

    group: Mapped["Group"] = relationship("Group", back_populates="group_students")
    student: Mapped["User"] = relationship("User")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    status: Mapped[GroupStatus] = mapped_column(SAEnum(GroupStatus), default=GroupStatus.active)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    schedule: Mapped[str | None] = mapped_column(String(200), nullable=True)
    room: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_students: Mapped[int] = mapped_column(Integer, default=20)
    group_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # standard|individual|online
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_month_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    teacher_salary_type: Mapped[str | None] = mapped_column(String(10), nullable=True)   # "percent" | "fixed"
    teacher_salary_value: Mapped[int | None] = mapped_column(Integer, nullable=True)     # % yoki so'm
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    group_link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attendance_topic_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    # Telegram bot orqali o'quvchi ro'yxatdan o'tish havolasi (masalan
    # https://t.me/fintechhublmsbot?start=<token>). Faqat shu ustunga tegishli
    # guruhga yozilish uchun ishlatiladi — boshqa hech qanday huquq bermaydi.
    invite_token: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    invite_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    course: Mapped["Course"] = relationship("Course", back_populates="groups")
    branch: Mapped["Branch"] = relationship("Branch", back_populates="groups", lazy="noload")
    teacher: Mapped["User"] = relationship("User", back_populates="taught_groups", foreign_keys=[teacher_id])
    group_students: Mapped[list["GroupStudent"]] = relationship("GroupStudent", back_populates="group", passive_deletes=True)
    attendances: Mapped[list["Attendance"]] = relationship("Attendance", back_populates="group", passive_deletes=True)
