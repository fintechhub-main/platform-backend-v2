import uuid
import enum
from sqlalchemy import String, Integer, Numeric, Date, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import date as DateType

from app.database import Base


class DiscountType(str, enum.Enum):
    percent = "percent"
    fixed = "fixed"


class DiscountStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    paused = "paused"


class Discount(Base):
    __tablename__ = "discounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    discount_type: Mapped[DiscountType] = mapped_column(SAEnum(DiscountType), default=DiscountType.percent)
    value: Mapped[int] = mapped_column(Integer)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    start_date: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    status: Mapped[DiscountStatus] = mapped_column(SAEnum(DiscountStatus), default=DiscountStatus.active)
    approved_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
