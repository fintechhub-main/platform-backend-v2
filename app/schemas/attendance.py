import uuid
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from app.models.attendance import AttendanceStatus


class AttendanceCreate(BaseModel):
    group_id: uuid.UUID
    student_id: uuid.UUID
    date: date
    status: AttendanceStatus = AttendanceStatus.present
    grade: Optional[int] = None


class AttendanceUpdate(BaseModel):
    status: Optional[AttendanceStatus] = None
    grade: Optional[int] = None
    reason: Optional[str] = None


class AttendanceOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    student_id: uuid.UUID
    date: date
    status: AttendanceStatus
    grade: Optional[int]
    reason: Optional[str] = None

    model_config = {"from_attributes": True}


class BulkAttendanceItem(BaseModel):
    student_id: uuid.UUID
    status: AttendanceStatus = AttendanceStatus.present
    grade: Optional[int] = None


class BulkAttendanceCreate(BaseModel):
    group_id: uuid.UUID
    date: date
    records: List[BulkAttendanceItem]
