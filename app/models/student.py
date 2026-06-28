import uuid
from datetime import date as date_type
from sqlalchemy import String, Text, Enum as SAEnum, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    trial = "trial"
    enrolled = "enrolled"
    rejected = "rejected"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(SAEnum(LeadStatus), default=LeadStatus.new)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # CRM extended fields
    course_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stage: Mapped[str] = mapped_column(String(30), default="yangi")   # yangi|aloqa|sinov|shartnoma|faol|rad
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    salesperson: Mapped["User"] = relationship("User", foreign_keys=[salesperson_id])
