import uuid
from pydantic import BaseModel
from typing import Optional

from app.models.homework import HomeworkStatus


class HomeworkCreate(BaseModel):
    lesson_id: uuid.UUID
    student_id: uuid.UUID
    answer_text: Optional[str] = None
    file_url: Optional[str] = None


class HomeworkUpdate(BaseModel):
    status: Optional[HomeworkStatus] = None
    grade: Optional[int] = None
    feedback: Optional[str] = None


class HomeworkOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    student_id: uuid.UUID
    answer_text: Optional[str]
    file_url: Optional[str]
    status: HomeworkStatus
    grade: Optional[int]
    feedback: Optional[str]

    model_config = {"from_attributes": True}
