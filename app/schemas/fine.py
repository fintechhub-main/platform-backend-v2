import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date
from app.schemas.user import UserOut


class FineCreate(BaseModel):
    user_id: uuid.UUID
    reason: str
    amount: int
    date: date
    note: Optional[str] = None


class FineUpdate(BaseModel):
    reason: Optional[str] = None
    amount: Optional[int] = None
    date: Optional[date] = None
    note: Optional[str] = None


class FineOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    reason: str
    amount: int
    date: date
    note: Optional[str]
    user: Optional[UserOut] = None

    model_config = {"from_attributes": True}
