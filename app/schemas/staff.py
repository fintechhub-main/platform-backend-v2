import uuid
import json
from typing import Any
from pydantic import BaseModel, field_validator


class StaffOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    phone: str
    email: str | None
    role: str

    status: str
    specializations: list[str]
    bio: str | None
    experience: str | None
    qualifications: list[str]
    rating: float
    monthly_earnings: int

    kpi_attendance: int
    kpi_results: int
    kpi_loss: int

    week_schedule: list[Any]
    performance_history: list[Any]
    salary_history: list[Any]

    @field_validator("specializations", "qualifications", "week_schedule", "performance_history", "salary_history", mode="before")
    @classmethod
    def parse_json(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return json.loads(v)
        return v or []

    model_config = {"from_attributes": True}


class StaffProfileUpdate(BaseModel):
    status: str | None = None
    specializations: list[str] | None = None
    bio: str | None = None
    experience: str | None = None
    qualifications: list[str] | None = None
    rating: float | None = None
    monthly_earnings: int | None = None
    kpi_attendance: int | None = None
    kpi_results: int | None = None
    kpi_loss: int | None = None
    week_schedule: list[Any] | None = None
    performance_history: list[Any] | None = None
    salary_history: list[Any] | None = None
