import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app.models.booking import BookingStatus
from app.schemas.user import UserOut


class BookingCreate(BaseModel):
    teacher_id: uuid.UUID
    topic: str
    date: date
    time_slot: str  # "10:00"
    note: Optional[str] = None


class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    note: Optional[str] = None


class BookingOut(BaseModel):
    id: uuid.UUID
    teacher_id: uuid.UUID
    student_id: uuid.UUID
    topic: str
    date: date
    time_slot: str
    status: BookingStatus
    note: Optional[str]
    teacher: Optional[UserOut] = None
    student: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class BusySlotsRequest(BaseModel):
    teacher_id: uuid.UUID
    date: date


class BusySlotsResponse(BaseModel):
    date: date
    busy_slots: list[str]
