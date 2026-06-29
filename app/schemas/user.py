import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from app.models.user import UserRole


class UserCreate(BaseModel):
    full_name: str
    phone: str
    email: Optional[str] = None
    password: str
    role: UserRole = UserRole.student
    branch_id: Optional[uuid.UUID] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = None
    student_status: Optional[str] = None
    passport: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    region: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    mother_name: Optional[str] = None
    mother_phone: Optional[str] = None
    father_name: Optional[str] = None
    father_phone: Optional[str] = None


class UserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    email: Optional[str]
    role: UserRole
    avatar: Optional[str]
    is_active: bool
    student_status: Optional[str] = None
    passport: Optional[str] = None
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    region: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    mother_name: Optional[str] = None
    mother_phone: Optional[str] = None
    father_name: Optional[str] = None
    father_phone: Optional[str] = None
    branch_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str
