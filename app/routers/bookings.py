import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import date

from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingUpdate, BookingOut, BusySlotsRequest, BusySlotsResponse
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/busy-slots", response_model=BusySlotsResponse)
async def busy_slots(
    teacher_id: uuid.UUID = Query(...),
    date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(Booking.time_slot).where(
            and_(
                Booking.teacher_id == teacher_id,
                Booking.date == date,
                Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
            )
        )
    )
    slots = [row[0] for row in result.all()]
    return BusySlotsResponse(date=date, busy_slots=slots)


@router.get("", response_model=List[BookingOut])
async def list_bookings(
    teacher_id: Optional[uuid.UUID] = Query(None),
    student_id: Optional[uuid.UUID] = Query(None),
    status: Optional[BookingStatus] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Booking).options(selectinload(Booking.teacher), selectinload(Booking.student))
    if current_user.role == "student":
        q = q.where(Booking.student_id == current_user.id)
    elif current_user.role == "teacher":
        q = q.where(Booking.teacher_id == current_user.id)
    else:
        if teacher_id:
            q = q.where(Booking.teacher_id == teacher_id)
        if student_id:
            q = q.where(Booking.student_id == student_id)
    if status:
        q = q.where(Booking.status == status)
    result = await db.execute(q.order_by(Booking.date.desc()))
    return result.scalars().all()


@router.post("", response_model=BookingOut, status_code=201)
async def create_booking(data: BookingCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # check slot is free
    existing = await db.execute(
        select(Booking).where(
            and_(
                Booking.teacher_id == data.teacher_id,
                Booking.date == data.date,
                Booking.time_slot == data.time_slot,
                Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Time slot is already booked")

    booking = Booking(**data.model_dump(), student_id=current_user.id)
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    result = await db.execute(
        select(Booking).options(selectinload(Booking.teacher), selectinload(Booking.student)).where(Booking.id == booking.id)
    )
    return result.scalar_one()


@router.patch("/{booking_id}", response_model=BookingOut)
async def update_booking(booking_id: uuid.UUID, data: BookingUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(booking, k, v)
    await db.commit()
    await db.refresh(booking)
    return booking
