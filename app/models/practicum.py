import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, ForeignKey, Date, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PracticumTeam(Base):
    __tablename__ = "practicum_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    mentor: Mapped[str] = mapped_column(String(200))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stack: Mapped[list] = mapped_column(JSON, default=list)
    links: Mapped[dict] = mapped_column(JSON, default=dict)
    members: Mapped[list] = mapped_column(JSON, default=list)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    branch: Mapped["Branch"] = relationship("Branch", lazy="noload")
    tasks: Mapped[list["PracticumTask"]] = relationship(
        "PracticumTask", back_populates="team", cascade="all, delete-orphan", lazy="noload"
    )


class PracticumTask(Base):
    __tablename__ = "practicum_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practicum_teams.id", ondelete="CASCADE"),
    )
    column: Mapped[str] = mapped_column(String(20), default="todo")  # todo/progress/review/done
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")  # high/medium/low
    tags: Mapped[list] = mapped_column(JSON, default=list)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    github: Mapped[str | None] = mapped_column(String(500), nullable=True)
    figma: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assignees: Mapped[list] = mapped_column(JSON, default=list)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    comments: Mapped[list] = mapped_column(JSON, default=list)
    activity: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team: Mapped["PracticumTeam"] = relationship("PracticumTeam", back_populates="tasks", lazy="noload")
