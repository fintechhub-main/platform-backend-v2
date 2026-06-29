import uuid
from sqlalchemy import String, Text, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    duration_months: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)

    groups: Mapped[list["Group"]] = relationship("Group", back_populates="course")
    modules: Mapped[list["Module"]] = relationship("Module", back_populates="course", order_by="Module.order")
