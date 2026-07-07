import uuid
from pydantic import BaseModel, model_validator
from typing import Optional, List
from datetime import date
from app.models.group import GroupStatus
from app.schemas.user import UserOut
from app.schemas.course import CourseOut


class GroupCreate(BaseModel):
    name: str
    course_id: uuid.UUID
    teacher_id: uuid.UUID
    status: GroupStatus = GroupStatus.active
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    schedule: Optional[str] = None
    room: Optional[str] = None
    max_students: int = 20
    group_type: Optional[str] = None
    price: Optional[int] = None
    first_month_price: Optional[int] = None
    payment_day: Optional[int] = None
    payment_start_date: Optional[date] = None
    teacher_salary_type: Optional[str] = None
    teacher_salary_value: Optional[int] = None
    description: Optional[str] = None
    group_link: Optional[str] = None
    chat_id: Optional[str] = None
    attendance_topic_id: Optional[str] = None
    branch_id: Optional[uuid.UUID] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    course_id: Optional[uuid.UUID] = None
    teacher_id: Optional[uuid.UUID] = None
    status: Optional[GroupStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    schedule: Optional[str] = None
    room: Optional[str] = None
    max_students: Optional[int] = None
    group_type: Optional[str] = None
    price: Optional[int] = None
    first_month_price: Optional[int] = None
    payment_day: Optional[int] = None
    payment_start_date: Optional[date] = None
    teacher_salary_type: Optional[str] = None
    teacher_salary_value: Optional[int] = None
    description: Optional[str] = None
    group_link: Optional[str] = None
    chat_id: Optional[str] = None
    attendance_topic_id: Optional[str] = None
    branch_id: Optional[uuid.UUID] = None


class GroupSlim(BaseModel):
    id: uuid.UUID
    name: str
    teacher_name: Optional[str] = None
    schedule: Optional[str] = None

    model_config = {"from_attributes": True}


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    course_id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: Optional[str] = None
    course_title: Optional[str] = None
    status: GroupStatus
    start_date: Optional[date]
    end_date: Optional[date]
    schedule: Optional[str]
    schedule_days: Optional[str] = None   # e.g. "Du/Chor/Ju"
    schedule_time: Optional[str] = None   # e.g. "09:00–11:00"
    room: Optional[str]
    max_students: int
    student_count: int = 0
    group_type: Optional[str] = None
    price: Optional[int] = None
    first_month_price: Optional[int] = None
    payment_day: Optional[int] = None
    payment_start_date: Optional[date] = None
    teacher_salary_type: Optional[str] = None
    teacher_salary_value: Optional[int] = None
    description: Optional[str] = None
    group_link: Optional[str] = None
    chat_id: Optional[str] = None
    attendance_topic_id: Optional[str] = None
    branch_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _parse_schedule(self):
        if self.schedule:
            parts = self.schedule.split(" ", 1)
            self.schedule_days = parts[0]
            self.schedule_time = parts[1] if len(parts) > 1 else None
        return self


class GroupDetailOut(GroupOut):
    course: Optional[CourseOut] = None
    teacher: Optional[UserOut] = None
    student_count: int = 0
