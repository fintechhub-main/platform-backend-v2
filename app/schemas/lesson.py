import uuid
import json
from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from app.models.lesson import LessonType


class ModuleCreate(BaseModel):
    course_id: uuid.UUID
    title: str
    order: int = 0
    is_open: bool = False


class ModuleUpdate(BaseModel):
    title: Optional[str] = None
    order: Optional[int] = None
    is_open: Optional[bool] = None


class ModuleOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    order: int
    is_open: bool

    model_config = {"from_attributes": True}


class LessonCreate(BaseModel):
    module_id: uuid.UUID
    title: str
    type: LessonType
    order: int = 0
    is_open: bool = False
    duration: Optional[str] = None
    video_url: Optional[str] = None
    content: Optional[str] = None
    code_lang: Optional[str] = None
    has_terminal: bool = False
    exam_type: Optional[str] = None


class LessonUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[LessonType] = None
    order: Optional[int] = None
    is_open: Optional[bool] = None
    duration: Optional[str] = None
    video_url: Optional[str] = None
    content: Optional[str] = None
    code_lang: Optional[str] = None
    has_terminal: Optional[bool] = None
    exam_type: Optional[str] = None


class LessonOut(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    type: LessonType
    order: int
    is_open: bool
    duration: Optional[str]
    video_url: Optional[str]
    content: Optional[str]
    code_lang: Optional[str]
    has_terminal: bool
    exam_type: Optional[str]

    model_config = {"from_attributes": True}


class QuizQuestionCreate(BaseModel):
    question: str
    options: List[str]
    correct_index: int
    order: int = 0


class QuizQuestionUpdate(BaseModel):
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_index: Optional[int] = None
    order: Optional[int] = None


class QuizQuestionOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    question: str
    options: List[str]
    correct_index: int
    order: int

    @field_validator("options", mode="before")
    @classmethod
    def parse_options(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v or []

    model_config = {"from_attributes": True}


class LessonWithQuiz(LessonOut):
    quiz_questions: List[QuizQuestionOut] = []


class ModuleWithLessons(ModuleOut):
    lessons: List[LessonWithQuiz] = []
