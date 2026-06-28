import uuid
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date as Date, datetime

from app.models.payment import PaymentType, PaymentMethod


class PaymentCreate(BaseModel):
    student_id: uuid.UUID
    group_id: Optional[uuid.UUID] = None
    amount: int
    payment_type: PaymentType = PaymentType.monthly
    method: PaymentMethod = PaymentMethod.cash
    date: Date
    description: Optional[str] = None
    received_by_id: Optional[uuid.UUID] = None


class PaymentUpdate(BaseModel):
    amount: Optional[int] = None
    payment_type: Optional[PaymentType] = None
    method: Optional[PaymentMethod] = None
    date: Optional[Date] = None
    description: Optional[str] = None


class PaymentRefundCreate(BaseModel):
    amount: int
    reason: Optional[str] = None


class PaymentRefundOut(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    refunded_by_id: uuid.UUID
    refunded_by_name: Optional[str] = None
    amount: int
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    group_id: Optional[uuid.UUID]
    amount: int
    payment_type: PaymentType
    method: PaymentMethod
    date: Date
    description: Optional[str]
    received_by_id: Optional[uuid.UUID]
    created_by_id: Optional[uuid.UUID] = None
    updated_by_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    student_name: Optional[str] = None
    student_phone: Optional[str] = None
    group_name: Optional[str] = None
    teacher_name: Optional[str] = None
    received_by_name: Optional[str] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    total_refunded: Optional[int] = None
    discount_snapshot: Optional[List[Any]] = None
    logs: Optional[List[Any]] = None
    refunds: Optional[List[PaymentRefundOut]] = None

    model_config = {"from_attributes": True}
