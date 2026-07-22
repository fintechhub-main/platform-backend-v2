import uuid
import enum
import datetime
from typing import Optional
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class HomeworkType(str, enum.Enum):
    text   = "text"    # free-text answer
    file   = "file"    # any file upload
    image  = "image"   # image upload
    github = "github"  # GitHub repo URL
    code   = "code"    # code writing (editor)
    quiz   = "quiz"    # multiple-choice quiz


class SubmissionStatus(str, enum.Enum):
    pending   = "pending"
    submitted = "submitted"
    graded    = "graded"
    rejected  = "rejected"


class LessonHomework(Base):
    __tablename__ = "lesson_homework"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[HomeworkType] = mapped_column(SAEnum(HomeworkType), default=HomeworkType.text)
    max_score: Mapped[int] = mapped_column(Integer, default=100)
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # quiz questions, code template
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LessonHomeworkSubmission(Base):
    __tablename__ = "lesson_homework_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lesson_homework.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    text_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    code_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quiz_answers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # AI taklif qilgan baho — ustoz o'zgartirsa ham tarix sifatida saqlanadi
    ai_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    graded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    status: Mapped[SubmissionStatus] = mapped_column(SAEnum(SubmissionStatus), default=SubmissionStatus.pending)
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
