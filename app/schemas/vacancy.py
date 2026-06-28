import uuid
from pydantic import BaseModel
from typing import Optional, List
from app.models.vacancy import ApplicantStatus


class VacancyCreate(BaseModel):
    title: str
    department: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    is_active: bool = True


class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    is_active: Optional[bool] = None


class VacancyOut(BaseModel):
    id: uuid.UUID
    title: str
    department: Optional[str]
    description: Optional[str]
    requirements: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    is_active: bool
    applicant_count: int = 0

    model_config = {"from_attributes": True}


class ApplicantCreate(BaseModel):
    vacancy_id: uuid.UUID
    full_name: str
    phone: str
    email: Optional[str] = None
    resume_url: Optional[str] = None
    note: Optional[str] = None


class ApplicantUpdate(BaseModel):
    status: Optional[ApplicantStatus] = None
    note: Optional[str] = None


class ApplicantOut(BaseModel):
    id: uuid.UUID
    vacancy_id: uuid.UUID
    full_name: str
    phone: str
    email: Optional[str]
    resume_url: Optional[str]
    status: ApplicantStatus
    note: Optional[str]

    model_config = {"from_attributes": True}
