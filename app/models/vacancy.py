import uuid
from sqlalchemy import String, Text, Integer, Boolean, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class ApplicantStatus(str, enum.Enum):
    new = "new"
    interview = "interview"
    hired = "hired"
    rejected = "rejected"


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    applicants: Mapped[list["VacancyApplicant"]] = relationship("VacancyApplicant", back_populates="vacancy")


class VacancyApplicant(Base):
    __tablename__ = "vacancy_applicants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vacancy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vacancies.id", ondelete="CASCADE"))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resume_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ApplicantStatus] = mapped_column(SAEnum(ApplicantStatus), default=ApplicantStatus.new)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="applicants")
