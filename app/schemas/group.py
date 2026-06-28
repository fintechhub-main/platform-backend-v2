import uuid
from pydantic import BaseModel
from typing import Optional
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


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    course_id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: Optional[str] = None
    status: GroupStatus
    start_date: Optional[date]
    end_date: Optional[date]
    schedule: Optional[str]
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


class GroupDetailOut(GroupOut):
    course: Optional[CourseOut] = None
    teacher: Optional[UserOut] = None
    student_count: int = 0
