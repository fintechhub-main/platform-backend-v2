import uuid
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ExamQuestionIn(BaseModel):
    question: str
    options: List[str]
    correct_index: int


class ExamCreate(BaseModel):
    lesson_id: uuid.UUID
    title: str
    type: Optional[str] = None
    date: Optional[str] = None   # YYYY-MM-DD
    time: Optional[str] = None   # HH:mm
    duration_minutes: int = 60
    pass_percent: int = 70
    questions: List[ExamQuestionIn] = []


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    duration_minutes: Optional[int] = None
    pass_percent: Optional[int] = None
    questions: Optional[List[ExamQuestionIn]] = None  # berilsa — savollar to'liq almashtiriladi


class ExamQuestionOut(BaseModel):
    id: uuid.UUID
    question: str
    options: list  # parsed from JSON
    correct_index: int
    order: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_q(cls, q):
        import json
        try:
            opts = json.loads(q.options) if isinstance(q.options, str) else q.options
        except Exception:
            opts = []
        return cls(id=q.id, question=q.question, options=opts, correct_index=q.correct_index, order=q.order)


class ExamDraftOut(BaseModel):
    answers: List[int]
    time_remaining_seconds: int
    started_at: datetime

    model_config = {"from_attributes": True}


class ExamOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    duration_minutes: int
    pass_percent: int
    questions: List[ExamQuestionOut] = []
    draft: Optional[ExamDraftOut] = None

    model_config = {"from_attributes": True}


class ExamSubmissionCreate(BaseModel):
    answers: List[int]  # [-1 = javob berilmagan]
    time_spent_seconds: Optional[int] = None


class ExamSubmissionOut(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    student_id: uuid.UUID
    score: int
    passed: bool
    time_spent_seconds: Optional[int]

    model_config = {"from_attributes": True}


class ExamDraftIn(BaseModel):
    answers: List[int]
    time_remaining_seconds: int
