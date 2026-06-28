import uuid
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Branch(Base):
    __tablename__ = "branches"

    id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:    Mapped[str]       = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    color:   Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool]    = mapped_column(default=True)

    groups: Mapped[list["Group"]] = relationship("Group", back_populates="branch", lazy="noload")
