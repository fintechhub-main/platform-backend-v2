import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from datetime import date
from pydantic import BaseModel

from app.database import get_db
from app.models.attendance import Attendance
from app.models.group import Group
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate, AttendanceOut, BulkAttendanceCreate
from app.dependencies import get_current_user, require_admin_or_teacher

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("", response_model=List[AttendanceOut])
async def list_attendance(
    group_id: uuid.UUID = Query(None),
    date_from: date = Query(None),
    date_to: date = Query(None),
    student_id: uuid.UUID = Query(None),
    status: str = Query(None),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if not group_id and not student_id and not date_from and not branch_id:
        raise HTTPException(status_code=400, detail="group_id, student_id yoki date_from kerak")
    q = select(Attendance)
    if group_id:
        q = q.where(Attendance.group_id == group_id)
    if student_id:
        q = q.where(Attendance.student_id == student_id)
    if date_from:
        q = q.where(Attendance.date >= date_from)
    if date_to:
        q = q.where(Attendance.date <= date_to)
    if status:
        q = q.where(Attendance.status == status)
    if branch_id:
        q = (
            q.join(Group, Group.id == Attendance.group_id)
            .where(Group.branch_id == uuid.UUID(branch_id))
        )
    result = await db.execute(q.order_by(Attendance.date.desc()))
    return result.scalars().all()


class StudentAttendanceStat(BaseModel):
    student_id: uuid.UUID
    total: int
    present: int
    attendance_pct: float
    grade_avg: Optional[float]


@router.get("/student-stats", response_model=List[StudentAttendanceStat])
async def student_attendance_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Per-student aggregated attendance stats."""
    from sqlalchemy import case
    rows = (await db.execute(
        select(
            Attendance.student_id,
            func.count().label("total"),
            func.sum(
                case((Attendance.status.in_(["present", "online", "late"]), 1), else_=0)
            ).label("present"),
            func.avg(Attendance.grade).label("grade_avg"),
        ).group_by(Attendance.student_id)
    )).all()

    result = []
    for row in rows:
        total   = row.total or 0
        present = int(row.present or 0)
        result.append(StudentAttendanceStat(
            student_id     = row.student_id,
            total          = total,
            present        = present,
            attendance_pct = round(present / total * 100, 1) if total > 0 else 0.0,
            grade_avg      = round(float(row.grade_avg), 1) if row.grade_avg is not None else None,
        ))
    return result


@router.post("", response_model=AttendanceOut, status_code=201)
async def create_attendance(data: AttendanceCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    att = Attendance(**data.model_dump())
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return att


@router.post("/bulk", response_model=List[AttendanceOut], status_code=201)
async def bulk_attendance(data: BulkAttendanceCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    created = []
    for item in data.records:
        existing = await db.execute(
            select(Attendance).where(
                and_(Attendance.group_id == data.group_id,
                     Attendance.student_id == item.student_id,
                     Attendance.date == data.date)
            )
        )
        att = existing.scalar_one_or_none()
        if att:
            att.status = item.status
            att.grade = item.grade
        else:
            att = Attendance(group_id=data.group_id, date=data.date, **item.model_dump())
            db.add(att)
        created.append(att)
    await db.commit()
    for att in created:
        await db.refresh(att)
    return created


@router.patch("/{att_id}", response_model=AttendanceOut)
async def update_attendance(att_id: uuid.UUID, data: AttendanceUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Attendance).where(Attendance.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(att, k, v)
    await db.commit()
    await db.refresh(att)
    return att
