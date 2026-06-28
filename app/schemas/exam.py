import uuid
from pydantic import BaseModel
from typing import Optional, List


class ExamCreate(BaseModel):
    lesson_id: uuid.UUID
    title: str
    duration_minutes: int = 60
    pass_percent: int = 70


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    duration_minutes: Optional[int] = None
    pass_percent: Optional[int] = None


class ExamOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    duration_minutes: int
    pass_percent: int

    model_config = {"from_attributes": True}


class ExamSubmissionCreate(BaseModel):
    answers: str
    time_spent_seconds: Optional[int] = None


class ExamSubmissionOut(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    student_id: uuid.UUID
    answers: str
    score: Optional[int]
    passed: bool
    time_spent_seconds: Optional[int]

    model_config = {"from_attributes": True}
