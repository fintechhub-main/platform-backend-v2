import uuid
from sqlalchemy import String, Integer, Boolean, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class RoomStatus(str, enum.Enum):
    available = "available"
    occupied  = "occupied"
    repair    = "repair"
    closed    = "closed"


class RoomType(str, enum.Enum):
    classroom  = "classroom"
    lab        = "lab"
    conference = "conference"
    computer   = "computer"


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    floor: Mapped[str] = mapped_column(String(30))          # "1-qavat"
    type: Mapped[RoomType] = mapped_column(SAEnum(RoomType))
    capacity: Mapped[int] = mapped_column(Integer)
    status: Mapped[RoomStatus] = mapped_column(SAEnum(RoomStatus), default=RoomStatus.available)
    amenities: Mapped[str] = mapped_column(Text, default="[]")   # JSON list
    current_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_free: Mapped[str | None] = mapped_column(String(20), nullable=True)
    schedule: Mapped[str] = mapped_column(Text, default="[]")    # JSON list of {group,from,to}
    weekly: Mapped[str] = mapped_column(Text, default="{}")      # JSON weekly map
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
