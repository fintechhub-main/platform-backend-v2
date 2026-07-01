import uuid
from sqlalchemy import String, Boolean, Enum as SAEnum, Date, DateTime, func, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from datetime import date as DateType, datetime
from typing import Optional

from app.database import Base


class UserRole(str, enum.Enum):
    superadmin = "superadmin"
    admin = "admin"
    manager = "manager"
    teacher = "teacher"
    assistant_teacher = "assistant_teacher"
    cashier = "cashier"
    student = "student"
    staff = "staff"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.student, index=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    student_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    passport: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birth_date: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mother_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mother_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    father_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    father_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")

    taught_groups: Mapped[list["Group"]] = relationship("Group", back_populates="teacher", foreign_keys="Group.teacher_id")
    fines: Mapped[list["Fine"]] = relationship("Fine", back_populates="user")
    bookings_as_teacher: Mapped[list["Booking"]] = relationship("Booking", back_populates="teacher", foreign_keys="Booking.teacher_id")
    bookings_as_student: Mapped[list["Booking"]] = relationship("Booking", back_populates="student", foreign_keys="Booking.student_id")
