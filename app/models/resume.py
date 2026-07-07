import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    linkedin: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    skills: Mapped[Optional[list]] = mapped_column(JSONB, default=list, nullable=True)
    interests: Mapped[Optional[list]] = mapped_column(JSONB, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    education: Mapped[list["ResumeEducation"]] = relationship("ResumeEducation", back_populates="resume", cascade="all, delete-orphan")
    work_experience: Mapped[list["ResumeWorkExperience"]] = relationship("ResumeWorkExperience", back_populates="resume", cascade="all, delete-orphan")
    leadership: Mapped[list["ResumeLeadership"]] = relationship("ResumeLeadership", back_populates="resume", cascade="all, delete-orphan")


class ResumeEducation(Base):
    __tablename__ = "resume_education"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    university: Mapped[str] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    degree: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    year: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    course_work: Mapped[Optional[list]] = mapped_column(JSONB, default=list, nullable=True)

    resume: Mapped["Resume"] = relationship("Resume", back_populates="education")


class ResumeWorkExperience(Base):
    __tablename__ = "resume_work_experience"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    achievements: Mapped[Optional[list]] = mapped_column(JSONB, default=list, nullable=True)

    resume: Mapped["Resume"] = relationship("Resume", back_populates="work_experience")


class ResumeLeadership(Base):
    __tablename__ = "resume_leadership"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    achievements: Mapped[Optional[list]] = mapped_column(JSONB, default=list, nullable=True)

    resume: Mapped["Resume"] = relationship("Resume", back_populates="leadership")
