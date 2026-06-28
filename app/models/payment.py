import uuid
import enum
import datetime

from sqlalchemy import Integer, Text, ForeignKey, Enum as SAEnum, Date, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaymentType(str, enum.Enum):
    monthly = "monthly"
    registration = "registration"
    material = "material"
    other = "other"


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    card = "card"
    transfer = "transfer"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    payment_type: Mapped[PaymentType] = mapped_column(SAEnum(PaymentType), default=PaymentType.monthly)
    method: Mapped[PaymentMethod] = mapped_column(SAEnum(PaymentMethod), default=PaymentMethod.cash)
    date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    discount_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)

    student:     Mapped["User"] = relationship("User", foreign_keys=[student_id],    lazy="noload")
    group:       Mapped["Group"] = relationship("Group",                              lazy="noload")
    received_by: Mapped["User"] = relationship("User", foreign_keys=[received_by_id],lazy="noload")
    created_by:  Mapped["User"] = relationship("User", foreign_keys=[created_by_id], lazy="noload")
    updated_by:  Mapped["User"] = relationship("User", foreign_keys=[updated_by_id], lazy="noload")
    refunds:     Mapped[list["PaymentRefund"]] = relationship("PaymentRefund", back_populates="payment", cascade="all, delete-orphan", lazy="noload")


class PaymentRefund(Base):
    __tablename__ = "payment_refunds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"))
    refunded_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    payment:     Mapped["Payment"] = relationship("Payment", back_populates="refunds", lazy="noload")
    refunded_by: Mapped["User"]   = relationship("User", foreign_keys=[refunded_by_id], lazy="noload")
