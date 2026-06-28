import uuid
from datetime import date
from sqlalchemy import String, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"))
    template: Mapped[str] = mapped_column(String(30), default="classic")
    issued_date: Mapped[date] = mapped_column(Date)
    serial_number: Mapped[str] = mapped_column(String(50), unique=True)

    student: Mapped["User"] = relationship("User")
    course: Mapped["Course"] = relationship("Course")
