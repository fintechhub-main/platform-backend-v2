import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, union, cast, String
from typing import List, Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.models.group import Group, GroupStudent
from app.models.staff_profile import StaffProfile
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.dependencies import get_current_user, require_admin, require_permission
from app.utils.auth import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(data: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    for key, val in data.model_dump(exclude_none=True).items():
        setattr(current_user, key, val)
    await db.commit()
    await db.refresh(current_user)
    return current_user


def _build_user_query(role, search, is_active, student_status, in_group, branch_id, group_id=None, course_id=None):
    q = select(User)
    if role:
        try:
            q = q.where(User.role == UserRole(role))
        except ValueError:
            q = q.where(cast(User.role, String) == role)
    if search:
        q = q.where(User.full_name.ilike(f"%{search}%") | User.phone.ilike(f"%{search}%"))
    if is_active is not None:
        q = q.where(User.is_active == is_active)
    if student_status is not None:
        q = q.where(User.student_status == student_status)
    if group_id:
        q = q.where(User.id.in_(select(GroupStudent.student_id).where(GroupStudent.group_id == group_id)))
    if course_id:
        q = q.where(User.id.in_(
            select(GroupStudent.student_id)
            .join(Group, Group.id == GroupStudent.group_id)
            .where(Group.course_id == course_id)
        ))
    if in_group is True:
        q = q.where(User.id.in_(select(GroupStudent.student_id).distinct()))
    elif in_group is False:
        q = q.where(User.id.not_in(select(GroupStudent.student_id).distinct()))
    if branch_id:
        branch_uuid = uuid.UUID(branch_id)
        if role == 'student':
            q = q.where(
                (User.branch_id == branch_uuid) |
                User.id.in_(
                    select(GroupStudent.student_id)
                    .join(Group, Group.id == GroupStudent.group_id)
                    .where(Group.branch_id == branch_uuid)
                )
            )
        elif role == 'teacher':
            q = q.where(
                (User.branch_id == branch_uuid) |
                User.id.in_(select(Group.teacher_id).where(Group.branch_id == branch_uuid))
            )
        else:
            student_subq = (
                select(GroupStudent.student_id.label("id"))
                .join(Group, Group.id == GroupStudent.group_id)
                .where(Group.branch_id == branch_uuid)
            )
            teacher_subq = (
                select(Group.teacher_id.label("id"))
                .where(Group.branch_id == branch_uuid, Group.teacher_id.isnot(None))
            )
            combined = union(student_subq, teacher_subq).subquery()
            q = q.where(
                (User.branch_id == branch_uuid) |
                User.id.in_(select(combined.c.id))
            )
    return q


@router.get("/count")
async def count_users(
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    student_status: Optional[str] = Query(None),
    in_group: Optional[bool] = Query(None),
    branch_id: Optional[str] = Query(None),
    group_id: Optional[uuid.UUID] = Query(None),
    course_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("students", "view")),
):
    q = _build_user_query(role, search, is_active, student_status, in_group, branch_id, group_id, course_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    return {"total": total}


@router.get("/student-counts")
async def student_status_counts(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(User.student_status, func.count(User.id)).where(User.role == UserRole.student)
    if branch_id:
        branch_uuid = uuid.UUID(branch_id)
        q = q.where(
            (User.branch_id == branch_uuid) |
            User.id.in_(
                select(GroupStudent.student_id)
                .join(Group, Group.id == GroupStudent.group_id)
                .where(Group.branch_id == branch_uuid)
            )
        )
    q = q.group_by(User.student_status)
    rows = (await db.execute(q)).all()
    counts = {status: cnt for status, cnt in rows}
    total = sum(counts.values())
    return {
        "total":     total,
        "active":    counts.get("active", 0),
        "pending":   counts.get("pending", 0),
        "frozen":    counts.get("frozen", 0),
        "graduated": counts.get("graduated", 0),
        "dropped":   counts.get("dropped", 0),
    }


@router.get("/slim")
async def list_users_slim(
    role: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    in_group: Optional[bool] = Query(None),
    student_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Lightweight user list — returns only id and full_name for picker dropdowns."""
    q = select(User.id, User.full_name)
    if role:
        try:
            q = q.where(User.role == UserRole(role))
        except ValueError:
            q = q.where(cast(User.role, String) == role)
    if search:
        q = q.where(User.full_name.ilike(f"%{search}%") | User.phone.ilike(f"%{search}%"))
    if student_status:
        q = q.where(User.student_status == student_status)
    if in_group is True:
        q = q.where(User.id.in_(select(GroupStudent.student_id).distinct()))
    elif in_group is False:
        q = q.where(User.id.not_in(select(GroupStudent.student_id).distinct()))
    if branch_id:
        branch_uuid = uuid.UUID(branch_id)
        if role == 'student':
            q = q.where(
                (User.branch_id == branch_uuid) |
                User.id.in_(
                    select(GroupStudent.student_id)
                    .join(Group, Group.id == GroupStudent.group_id)
                    .where(Group.branch_id == branch_uuid)
                )
            )
        else:
            q = q.where(User.branch_id == branch_uuid)
    result = await db.execute(q.order_by(User.full_name))
    return [{"id": str(row.id), "full_name": row.full_name} for row in result.all()]


@router.get("", response_model=List[UserOut])
async def list_users(
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    student_status: Optional[str] = Query(None),
    in_group: Optional[bool] = Query(None),
    branch_id: Optional[str] = Query(None),
    group_id: Optional[uuid.UUID] = Query(None),
    course_id: Optional[uuid.UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = _build_user_query(role, search, is_active, student_status, in_group, branch_id, group_id, course_id)
    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.execute(select(User).where(User.phone == data.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Bu telefon raqam allaqachon ro'yxatdan o'tgan")
    if data.email:
        email_existing = await db.execute(select(User).where(User.email == data.email))
        if email_existing.scalar_one_or_none():
            raise HTTPException(400, "Bu email allaqachon ro'yxatdan o'tgan")
    user = User(**data.model_dump(exclude={"password"}), password_hash=hash_password(data.password))
    if data.role == UserRole.student:
        user.student_status = "active"
    db.add(user)
    await db.flush()  # get user.id before commit

    # Auto-create staff profile for teacher/assistant_teacher/staff roles
    if data.role in (UserRole.teacher, UserRole.assistant_teacher, UserRole.staff):
        profile = StaffProfile(user_id=user.id)
        db.add(profile)

    await db.commit()
    await db.refresh(user)
    # Refresh qaytadan yuklasin (branch_id lazy load muammosi)
    result2 = await db.execute(select(User).where(User.id == user.id))
    return result2.scalar_one()


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if str(current_user.id) != str(user_id) and str(current_user.role) not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, data: UserUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    for key, val in data.model_dump(exclude_none=True).items():
        setattr(user, key, val)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    await db.delete(user)
    await db.commit()
