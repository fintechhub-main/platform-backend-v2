import uuid
from pydantic import BaseModel
from typing import Optional


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    image: Optional[str] = None
    price: int = 0
    duration_months: int = 3
    is_active: bool = True


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    price: Optional[int] = None
    duration_months: Optional[int] = None
    is_active: Optional[bool] = None


class CourseOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    image: Optional[str]
    price: int
    duration_months: int
    is_active: bool

    model_config = {"from_attributes": True}
