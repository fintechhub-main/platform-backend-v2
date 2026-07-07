import uuid
import secrets
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Numeric, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CARD_PREFIX = "8600"
INITIAL_BALANCE = Decimal("100000.00")


def _generate_card_number() -> str:
    body = "".join(secrets.choice("0123456789") for _ in range(12))
    return f"{CARD_PREFIX}{body}"


def _generate_expire() -> str:
    today = date.today()
    year = (today.year + 5) % 100
    return f"{today.month:02d}{year:02d}"


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    card_number: Mapped[str] = mapped_column(String(16), unique=True)
    holder_name: Mapped[str] = mapped_column(String(128))
    expire: Mapped[str] = mapped_column(String(4))
    balance: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=INITIAL_BALANCE)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    sent_transfers: Mapped[list["CardTransfer"]] = relationship("CardTransfer", back_populates="from_card", foreign_keys="CardTransfer.from_card_id")
    received_transfers: Mapped[list["CardTransfer"]] = relationship("CardTransfer", back_populates="to_card", foreign_keys="CardTransfer.to_card_id")


class CardTransfer(Base):
    __tablename__ = "card_transfers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    to_card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    from_card: Mapped["Card"] = relationship("Card", back_populates="sent_transfers", foreign_keys=[from_card_id])
    to_card: Mapped["Card"] = relationship("Card", back_populates="received_transfers", foreign_keys=[to_card_id])
