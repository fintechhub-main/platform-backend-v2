import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # quiz|written|oral|practical|mock
    date: Mapped[str | None] = mapped_column("exam_date", String(10), nullable=True)  # YYYY-MM-DD
    time: Mapped[str | None] = mapped_column("exam_time", String(5), nullable=True)   # HH:mm
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    pass_percent: Mapped[int] = mapped_column(Integer, default=70)

    questions: Mapped[list["ExamQuestion"]] = relationship("ExamQuestion", back_populates="exam", order_by="ExamQuestion.order")
    submissions: Mapped[list["ExamSubmission"]] = relationship("ExamSubmission", back_populates="exam")
    drafts: Mapped[list["ExamDraft"]] = relationship("ExamDraft", back_populates="exam")


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text)  # JSON string
    correct_index: Mapped[int] = mapped_column(Integer)
    order: Mapped[int] = mapped_column(Integer, default=0)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="questions")

    def options_list(self) -> list:
        try:
            return json.loads(self.options)
        except Exception:
            return []


class ExamSubmission(Base):
    __tablename__ = "exam_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    answers: Mapped[str] = mapped_column(Text)  # JSON string [0, 2, -1, 1]
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))

    exam: Mapped["Exam"] = relationship("Exam", back_populates="submissions")
    student: Mapped["User"] = relationship("User")


class ExamDraft(Base):
    """Student imtihon jarayonida saqlab boradigan oraliq javoblar."""
    __tablename__ = "exam_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"))
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    answers: Mapped[str] = mapped_column(Text, default="[]")  # JSON string
    time_remaining_seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    exam: Mapped["Exam"] = relationship("Exam", back_populates="drafts")
