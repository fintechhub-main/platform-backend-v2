import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app.models.discount import DiscountType, DiscountStatus


class DiscountCreate(BaseModel):
    student_id: uuid.UUID
    group_id: Optional[uuid.UUID] = None
    discount_type: DiscountType = DiscountType.percent
    value: int
    reason: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: DiscountStatus = DiscountStatus.active
    approved_by: Optional[str] = None


class DiscountUpdate(BaseModel):
    discount_type: Optional[DiscountType] = None
    value: Optional[int] = None
    reason: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[DiscountStatus] = None
    approved_by: Optional[str] = None


class DiscountOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    group_id: Optional[uuid.UUID]
    discount_type: DiscountType
    value: int
    reason: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    status: DiscountStatus
    approved_by: Optional[str]
    student_name: Optional[str] = None
    student_phone: Optional[str] = None

    model_config = {"from_attributes": True}
