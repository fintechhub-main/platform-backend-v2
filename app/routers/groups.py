import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional

from app.database import get_db
from app.models.group import Group, GroupStudent
from app.models.user import User
from app.schemas.group import GroupCreate, GroupUpdate, GroupOut, GroupDetailOut, GroupSlim
from app.schemas.user import UserOut
from app.dependencies import get_current_user, require_admin, require_admin_or_teacher, require_permission
from app.utils.attendance_generator import generate_attendance_for_group

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/my", response_model=List[GroupOut])
async def my_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(Group)
        .join(GroupStudent, GroupStudent.group_id == Group.id)
        .where(GroupStudent.student_id == current_user.id)
        .order_by(Group.start_date.desc())
    )
    result = await db.execute(q)
    return result.scalars().all()


@router.get("", response_model=List[GroupOut])
async def list_groups(
    course_id: Optional[uuid.UUID] = Query(None),
    teacher_id: Optional[uuid.UUID] = Query(None),
    student_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0, limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("groups", "view")),
):
    q = (
        select(Group)
        .options(joinedload(Group.teacher), selectinload(Group.course), selectinload(Group.group_students))
    )
    if course_id:
        q = q.where(Group.course_id == course_id)
    if teacher_id:
        q = q.where(Group.teacher_id == teacher_id)
    if status:
        q = q.where(Group.status == status)
    if branch_id:
        q = q.where(Group.branch_id == uuid.UUID(branch_id))
    if student_id:
        q = q.join(GroupStudent, GroupStudent.group_id == Group.id).where(GroupStudent.student_id == student_id)
    result = await db.execute(q.offset(skip).limit(limit))
    groups = result.unique().scalars().all()
    out = []
    for g in groups:
        data = GroupOut.model_validate(g)
        data.teacher_name = g.teacher.full_name if g.teacher else None
        data.course_title = g.course.title if g.course else None
        data.student_count = len(g.group_students)
        out.append(data)
    return out


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    group = Group(**data.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    # Attendance guruhga student qo'shilganda yoki har kungi scheduler orqali yaratiladi
    return group


@router.get("/frozen-students", response_model=List[dict])
async def frozen_students(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(User, GroupStudent.group_id)
        .join(GroupStudent, GroupStudent.student_id == User.id)
        .where(GroupStudent.is_frozen == True)
    )
    if branch_id:
        q = q.join(Group, Group.id == GroupStudent.group_id).where(Group.branch_id == uuid.UUID(branch_id))
    result = await db.execute(q)
    rows = result.all()
    return [
        {
            "id": str(u.id),
            "full_name": u.full_name,
            "phone": u.phone,
            "group_id": str(gs_group_id),
        }
        for u, gs_group_id in rows
    ]


@router.get("/slim", response_model=List[GroupSlim])
async def list_groups_slim(
    branch_id: Optional[str] = Query(None),
    course_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Lightweight group list — only fields needed for filter dropdowns and student mapping."""
    q = select(Group).options(joinedload(Group.teacher))
    if branch_id:
        q = q.where(Group.branch_id == uuid.UUID(branch_id))
    if course_id:
        q = q.where(Group.course_id == course_id)
    if status:
        q = q.where(Group.status == status)
    result = await db.execute(q)
    groups = result.unique().scalars().all()
    return [
        GroupSlim(
            id=g.id,
            name=g.name,
            teacher_name=g.teacher.full_name if g.teacher else None,
            schedule=g.schedule,
        )
        for g in groups
    ]


@router.get("/{group_id}", response_model=GroupDetailOut)
async def get_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    from datetime import date
    result = await db.execute(
        select(Group)
        .options(selectinload(Group.course), selectinload(Group.teacher), selectinload(Group.group_students))
        .where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    # Bugun guruhning dars kuni bo'lsa, attendance yozuvlarini avtomatik yaratish
    if group.status == 'active':
        today = date.today()
        await generate_attendance_for_group(db, group, from_date=today, to_date=today)
    out = GroupDetailOut.model_validate(group)
    out.student_count = len(group.group_students)
    return out


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(group_id: uuid.UUID, data: GroupUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(group, k, v)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    from app.models.group import GroupStudent
    await db.execute(delete(GroupStudent).where(GroupStudent.group_id == group_id))
    await db.delete(group)
    await db.commit()


@router.get("/{group_id}/students")
async def group_students(
    group_id: uuid.UUID,
    is_frozen: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(User, GroupStudent.is_frozen)
        .join(GroupStudent, GroupStudent.student_id == User.id)
        .where(GroupStudent.group_id == group_id)
    )
    if is_frozen is not None:
        q = q.where(GroupStudent.is_frozen == is_frozen)
    rows = (await db.execute(q)).all()
    result = []
    for user, frozen in rows:
        data = UserOut.model_validate(user).model_dump()
        data["is_frozen"] = bool(frozen)
        result.append(data)
    return result


@router.patch("/{group_id}/students/{student_id}/freeze", status_code=200)
async def freeze_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(404, "Not found")
    gs.is_frozen = True
    await db.commit()
    return {"ok": True}


@router.patch("/{group_id}/students/{student_id}/unfreeze", status_code=200)
async def unfreeze_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(404, "Not found")
    gs.is_frozen = False
    await db.commit()
    return {"ok": True}


@router.post("/{group_id}/students/{student_id}", status_code=201)
async def add_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    from datetime import date
    existing = await db.execute(
        select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Student already in group")
    db.add(GroupStudent(group_id=group_id, student_id=student_id))
    await db.commit()
    # Student uchun o'tgan darslarni yaratish
    grp_res = await db.execute(select(Group).where(Group.id == group_id))
    grp = grp_res.scalar_one_or_none()
    if grp and grp.status == 'active':
        from app.utils.attendance_generator import parse_schedule_days, lesson_dates_between
        from app.models.attendance import Attendance, AttendanceStatus
        weekdays = parse_schedule_days(grp.schedule or '')
        if weekdays and grp.start_date:
            today = date.today()
            end = min(today, grp.end_date or today)
            dates = lesson_dates_between(grp.start_date, end, weekdays)
            from sqlalchemy import select as sa_select
            ex = await db.execute(
                sa_select(Attendance.date)
                .where(Attendance.group_id == group_id, Attendance.student_id == student_id)
            )
            existing_dates = {r for r in ex.scalars().all()}
            for d in dates:
                if d not in existing_dates:
                    db.add(Attendance(
                        group_id=group_id, student_id=student_id,
                        date=d, status=AttendanceStatus.absent, grade=None,
                    ))
            await db.commit()
    return {"ok": True}


@router.delete("/{group_id}/students/{student_id}", status_code=204)
async def remove_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(
        select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id)
    )
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(404, "Not found")
    await db.delete(gs)
    await db.commit()
