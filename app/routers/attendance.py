import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel

from app.database import get_db
from app.models.attendance import Attendance
from app.models.group import Group, GroupStudent
from app.models.user import User
from app.schemas.attendance import AttendanceCreate, AttendanceUpdate, AttendanceOut, BulkAttendanceCreate
from app.dependencies import get_current_user, require_permission
from app.utils.audit import write_log

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("/daily")
async def daily_attendance(
    group_id: uuid.UUID = Query(...),
    date: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("attendance", "view")),
):
    """Guruh o'quvchilari + ularning berilgan kun davomati."""
    att_date = datetime.strptime(date, "%Y-%m-%d").date()

    # All students in this group
    gs_rows = (await db.execute(
        select(GroupStudent, User)
        .join(User, User.id == GroupStudent.student_id)
        .where(GroupStudent.group_id == group_id)
        .order_by(User.full_name)
    )).all()

    # Existing attendance records for the date
    att_rows = (await db.execute(
        select(Attendance).where(
            and_(Attendance.group_id == group_id, Attendance.date == att_date)
        )
    )).scalars().all()
    att_map = {a.student_id: a for a in att_rows}

    result = []
    for gs, student in gs_rows:
        att = att_map.get(student.id)
        result.append({
            "id": str(att.id) if att else None,
            "student_id": str(student.id),
            "full_name": student.full_name,
            "phone": student.phone or "",
            "status": att.status.value if att and att.status else None,
            "grade": att.grade if att else None,
            "reason": att.reason if att else None,
        })
    return result


@router.get("/missed")
async def missed_attendance(
    date: str = Query(...),
    page: int = Query(1),
    page_size: int = Query(50),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("attendance", "view")),
):
    """Berilgan kunda kelmagan (absent/excused) talabalar."""
    att_date = datetime.strptime(date, "%Y-%m-%d").date()

    base_q = (
        select(Attendance, User, Group)
        .join(User, User.id == Attendance.student_id)
        .join(Group, Group.id == Attendance.group_id)
        .where(Attendance.date == att_date)
        .where(Attendance.status.in_(["absent", "excused"]))
    )
    if branch_id:
        base_q = base_q.where(Group.branch_id == uuid.UUID(branch_id))

    total = (await db.execute(select(func.count()).select_from(base_q.subquery()))).scalar()
    rows = (await db.execute(
        base_q.offset((page - 1) * page_size).limit(page_size)
    )).all()

    items = []
    for att, student, group in rows:
        items.append({
            "att_id": str(att.id),
            "student_id": str(student.id),
            "full_name": student.full_name,
            "phone": student.phone or "",
            "group_name": group.name,
            "date": att.date.isoformat(),
            "status": att.status.value if hasattr(att.status, "value") else str(att.status),
            "reason": att.reason or "",
        })
    return {"items": items, "total": total}


@router.get("", response_model=List[AttendanceOut])
async def list_attendance(
    group_id: uuid.UUID = Query(None),
    date_from: date = Query(None),
    date_to: date = Query(None),
    student_id: uuid.UUID = Query(None),
    status: str = Query(None),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("attendance", "view")),
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


@router.get("/my")
async def my_attendance(
    group_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Student's own attendance records + summary stats. No admin permission required."""
    from sqlalchemy import case as sa_case
    q = select(Attendance).where(Attendance.student_id == current_user.id)
    if group_id:
        q = q.where(Attendance.group_id == group_id)
    if date_from:
        q = q.where(Attendance.date >= date_from)
    if date_to:
        q = q.where(Attendance.date <= date_to)
    rows = (await db.execute(q.order_by(Attendance.date.desc()))).scalars().all()

    total   = len(rows)
    present = sum(1 for r in rows if str(r.status) in {"present", "online", "late"})
    absent  = sum(1 for r in rows if str(r.status) == "absent")
    grades  = [r.grade for r in rows if r.grade is not None]
    grade_avg = round(sum(grades) / len(grades), 1) if grades else None

    return {
        "records": [
            {
                "id": str(r.id),
                "group_id": str(r.group_id),
                "date": r.date.isoformat(),
                "status": str(r.status),
                "grade": r.grade,
                "note": r.note if hasattr(r, "note") else None,
            }
            for r in rows
        ],
        "stats": {
            "total": total,
            "present": present,
            "absent": absent,
            "attendance_pct": round(present / total * 100, 1) if total > 0 else 0.0,
            "grade_avg": grade_avg,
        },
    }


@router.post("", response_model=AttendanceOut, status_code=201)
async def create_attendance(data: AttendanceCreate, db: AsyncSession = Depends(get_db), current_user=Depends(require_permission("attendance", "create"))):
    att = Attendance(**data.model_dump())
    db.add(att)
    await write_log(
        db,
        user=current_user,
        action="attendance.create",
        target=f"student:{data.student_id}, group:{data.group_id}, date:{data.date}",
        detail=f"status={data.status}, grade={data.grade}",
    )
    await db.commit()
    await db.refresh(att)
    return att


@router.post("/bulk", response_model=List[AttendanceOut], status_code=201)
async def bulk_attendance(data: BulkAttendanceCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("attendance", "create"))):
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
        status_val = item.status.value if hasattr(item.status, "value") else str(item.status)
        safe_grade = None if status_val in _NO_GRADE_STATUSES else item.grade
        if att:
            att.status = item.status
            att.grade = safe_grade
        else:
            att = Attendance(group_id=data.group_id, date=data.date,
                             student_id=item.student_id, status=item.status, grade=safe_grade)
            db.add(att)
        created.append(att)
    await db.commit()
    for att in created:
        await db.refresh(att)
    return created


_NO_GRADE_STATUSES = {"absent", "excused"}


@router.patch("/{att_id}", response_model=AttendanceOut)
async def update_attendance(att_id: uuid.UUID, data: AttendanceUpdate, db: AsyncSession = Depends(get_db), current_user=Depends(require_permission("attendance", "update"))):
    result = await db.execute(select(Attendance).where(Attendance.id == att_id))
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(404, "Not found")
    changes = {k: v for k, v in data.model_dump(exclude_none=True).items()}

    # Determine effective status after this update
    new_status = changes.get("status")
    effective_status = (new_status.value if hasattr(new_status, "value") else str(new_status)) if new_status else \
                       (att.status.value if hasattr(att.status, "value") else str(att.status))

    if "grade" in changes and effective_status in _NO_GRADE_STATUSES:
        raise HTTPException(400, f"'{effective_status}' holatdagi talabaga baho qo'yib bo'lmaydi")

    # If status changes to absent/excused, clear any existing grade
    if new_status and effective_status in _NO_GRADE_STATUSES:
        changes.pop("grade", None)
        att.grade = None

    old_status = att.status
    old_grade = att.grade
    for k, v in changes.items():
        setattr(att, k, v)
    detail_parts = []
    if "status" in changes:
        old_s = old_status.value if hasattr(old_status, "value") else str(old_status)
        new_s = changes['status'].value if hasattr(changes['status'], "value") else str(changes['status'])
        detail_parts.append(f"davomat: {old_s}→{new_s}")
    if "grade" in changes:
        detail_parts.append(f"baho: {old_grade}→{changes['grade']}")
    if "reason" in changes:
        detail_parts.append(f"sabab: {changes['reason']}")
    await write_log(
        db,
        user=current_user,
        action="attendance.update",
        target=f"att_id:{att_id}, student:{att.student_id}, date:{att.date}",
        detail=", ".join(detail_parts) if detail_parts else "o'zgartirildi",
    )
    await db.commit()
    await db.refresh(att)
    return att
