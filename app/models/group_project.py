import uuid
from datetime import datetime, date as DateType
from typing import Optional
from sqlalchemy import String, Text, DateTime, Date, func, ForeignKey, Table, Column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Many-to-many: group_projects <-> users (students)
group_project_students = Table(
    "group_project_students",
    Base.metadata,
    Column("project_id", UUID(as_uuid=True), ForeignKey("group_projects.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-many: group_project_tasks <-> users (students)
group_project_task_students = Table(
    "group_project_task_students",
    Base.metadata,
    Column("task_id", UUID(as_uuid=True), ForeignKey("group_project_tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class GroupProject(Base):
    __tablename__ = "group_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    teacher_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    start_date: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    project_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    figma_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_repos: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teacher: Mapped[Optional["User"]] = relationship("User", foreign_keys=[teacher_id])
    students: Mapped[list["User"]] = relationship("User", secondary=group_project_students)
    tasks: Mapped[list["GroupProjectTask"]] = relationship("GroupProjectTask", back_populates="project")


class GroupProjectTask(Base):
    __tablename__ = "group_project_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("group_projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    deadline: Mapped[Optional[DateType]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["GroupProject"] = relationship("GroupProject", back_populates="tasks")
    students: Mapped[list["User"]] = relationship("User", secondary=group_project_task_students)
    comments: Mapped[list["TaskComment"]] = relationship("TaskComment", back_populates="task")


class TaskComment(Base):
    __tablename__ = "group_project_task_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("group_project_tasks.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["GroupProjectTask"] = relationship("GroupProjectTask", back_populates="comments")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
