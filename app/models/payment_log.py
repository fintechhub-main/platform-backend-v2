import uuid
import datetime
from sqlalchemy import Text, ForeignKey, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id:          Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id:  Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    field_name:  Mapped[str]                = mapped_column(String(64))
    old_value:   Mapped[str | None]         = mapped_column(Text, nullable=True)
    new_value:   Mapped[str | None]         = mapped_column(Text, nullable=True)
    changed_at:  Mapped[datetime.datetime]  = mapped_column(DateTime, default=datetime.datetime.utcnow)
