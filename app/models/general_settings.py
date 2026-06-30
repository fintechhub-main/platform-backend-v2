import uuid
from typing import Optional
from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GeneralSettings(Base):
    __tablename__ = "general_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_name: Mapped[Optional[str]] = mapped_column(String(200), default="EduPlatform Pro")
    language: Mapped[Optional[str]] = mapped_column(String(10), default="uz")
    timezone: Mapped[Optional[str]] = mapped_column(String(50), default="Asia/Tashkent")
    currency: Mapped[Optional[str]] = mapped_column(String(10), default="UZS")
    work_start: Mapped[Optional[str]] = mapped_column(String(5), default="08:00")
    work_end: Mapped[Optional[str]] = mapped_column(String(5), default="20:00")
    academic_year_start: Mapped[Optional[str]] = mapped_column(String(2), default="09")
    academic_year_end: Mapped[Optional[str]] = mapped_column(String(2), default="06")
    work_days: Mapped[Optional[str]] = mapped_column(String(20), default="1,2,3,4,5,6")

    # Notification settings
    notif_email: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    notif_sms: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    notif_telegram: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    notif_payment: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    notif_attendance: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    notif_exams: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)

    # Payment settings
    payment_methods: Mapped[Optional[str]] = mapped_column(String(200), default="cash,card", nullable=True)
    late_fee_percent: Mapped[Optional[str]] = mapped_column(String(10), default="0", nullable=True)
    payment_day: Mapped[Optional[str]] = mapped_column(String(5), default="1", nullable=True)
