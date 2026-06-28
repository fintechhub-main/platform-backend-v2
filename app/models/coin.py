import uuid
import enum
import datetime

from sqlalchemy import String, Integer, ForeignKey, Enum as SAEnum, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CoinTxnType(str, enum.Enum):
    earned = "earned"
    spent = "spent"
    bonus = "bonus"
    penalty = "penalty"


class CoinTransaction(Base):
    __tablename__ = "coin_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    coins: Mapped[int] = mapped_column(Integer)
    txn_type: Mapped[CoinTxnType] = mapped_column(SAEnum(CoinTxnType), default=CoinTxnType.earned)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)

    student: Mapped["User"] = relationship("User")
