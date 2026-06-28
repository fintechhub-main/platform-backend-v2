import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date


class LeadCreate(BaseModel):
    full_name: str
    phone: str
    source: Optional[str] = None
    course_name: Optional[str] = None
    stage: str = "yangi"
    notes: Optional[str] = None
    note: Optional[str] = None
    created_date: Optional[date] = None
    salesperson_id: Optional[uuid.UUID] = None


class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    course_name: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    note: Optional[str] = None
    salesperson_id: Optional[uuid.UUID] = None


class LeadOut(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    source: Optional[str]
    course_name: Optional[str]
    stage: str
    notes: Optional[str]
    note: Optional[str]
    created_date: Optional[date]
    salesperson_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}
