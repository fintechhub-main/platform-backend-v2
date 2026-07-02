import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.database import get_db
from app.models.room import Room, RoomStatus, RoomType
from app.schemas.room import RoomCreate, RoomUpdate, RoomOut
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _serialize(room_data: dict) -> dict:
    """Convert list/dict fields to JSON strings for DB storage."""
    out = dict(room_data)
    for field in ("amenities", "schedule", "weekly"):
        if field in out and not isinstance(out[field], str):
            out[field] = json.dumps(out[field], ensure_ascii=False)
    return out


@router.get("", response_model=List[RoomOut])
async def list_rooms(
    status: Optional[RoomStatus] = Query(None),
    type: Optional[RoomType] = Query(None),
    floor: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rooms", "view")),
):
    q = select(Room)
    if status:
        q = q.where(Room.status == status)
    if type:
        q = q.where(Room.type == type)
    if floor:
        q = q.where(Room.floor == floor)
    if branch_id:
        q = q.where(Room.branch_id == uuid.UUID(branch_id))
    if search:
        q = q.where((Room.code.ilike(f"%{search}%")) | (Room.name.ilike(f"%{search}%")))
    result = await db.execute(q.order_by(Room.floor, Room.code))
    return result.scalars().all()


@router.post("", response_model=RoomOut, status_code=201)
async def create_room(data: RoomCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("rooms", "create"))):
    existing = await db.execute(select(Room).where(Room.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Xona kodi '{data.code}' allaqachon mavjud")
    row = _serialize(data.model_dump())
    room = Room(**row)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/{room_id}", response_model=RoomOut)
async def get_room(room_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Xona topilmadi")
    return room


@router.patch("/{room_id}", response_model=RoomOut)
async def update_room(room_id: uuid.UUID, data: RoomUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("rooms", "update"))):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Xona topilmadi")
    updates = _serialize({k: v for k, v in data.model_dump(exclude_none=True).items()})
    for k, v in updates.items():
        setattr(room, k, v)
    await db.commit()
    await db.refresh(room)
    return room


@router.delete("/{room_id}", status_code=204)
async def delete_room(room_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("rooms", "delete"))):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Xona topilmadi")
    await db.delete(room)
    await db.commit()
