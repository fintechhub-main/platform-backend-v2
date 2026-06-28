import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app.schemas.user import UserOut
from app.schemas.course import CourseOut


class CertificateCreate(BaseModel):
    student_id: uuid.UUID
    course_id: uuid.UUID
    template: str = "classic"
    issued_date: date
    serial_number: Optional[str] = None


class CertificateOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    course_id: uuid.UUID
    template: str
    issued_date: date
    serial_number: str
    student: Optional[UserOut] = None
    course: Optional[CourseOut] = None

    model_config = {"from_attributes": True}
