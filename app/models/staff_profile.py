import uuid
from sqlalchemy import String, Text, Integer, Float, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class StaffStatus(str, enum.Enum):
    active    = "active"
    on_leave  = "on_leave"
    resigned  = "resigned"


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    status: Mapped[StaffStatus] = mapped_column(SAEnum(StaffStatus), default=StaffStatus.active)
    specializations: Mapped[str] = mapped_column(Text, default="[]")   # JSON list
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "5 yil"
    qualifications: Mapped[str] = mapped_column(Text, default="[]")    # JSON list
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_earnings: Mapped[int] = mapped_column(Integer, default=0)

    # KPI
    kpi_attendance: Mapped[int] = mapped_column(Integer, default=0)
    kpi_results: Mapped[int] = mapped_column(Integer, default=0)
    kpi_loss: Mapped[int] = mapped_column(Integer, default=0)

    # Extended JSON fields
    week_schedule: Mapped[str] = mapped_column(Text, default="[]")      # JSON
    performance_history: Mapped[str] = mapped_column(Text, default="[]") # JSON
    salary_history: Mapped[str] = mapped_column(Text, default="[]")      # JSON

    user: Mapped["User"] = relationship("User")
