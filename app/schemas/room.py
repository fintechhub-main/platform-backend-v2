import uuid
from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
import json

from app.models.room import RoomStatus, RoomType


class RoomCreate(BaseModel):
    code: str
    name: str
    floor: str
    type: RoomType
    capacity: int
    status: RoomStatus = RoomStatus.available
    amenities: List[str] = []
    current_group: Optional[str] = None
    next_free: Optional[str] = None
    schedule: List[Any] = []
    weekly: dict = {}
    branch_id: Optional[uuid.UUID] = None


class RoomUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    floor: Optional[str] = None
    type: Optional[RoomType] = None
    capacity: Optional[int] = None
    status: Optional[RoomStatus] = None
    amenities: Optional[List[str]] = None
    current_group: Optional[str] = None
    next_free: Optional[str] = None
    schedule: Optional[List[Any]] = None
    weekly: Optional[dict] = None


class RoomOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    floor: str
    type: RoomType
    capacity: int
    status: RoomStatus
    amenities: List[str]
    current_group: Optional[str]
    next_free: Optional[str]
    schedule: List[Any]
    weekly: dict
    branch_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}

    @field_validator("amenities", mode="before")
    @classmethod
    def parse_amenities(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v or []

    @field_validator("schedule", mode="before")
    @classmethod
    def parse_schedule(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v or []

    @field_validator("weekly", mode="before")
    @classmethod
    def parse_weekly(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v or {}
