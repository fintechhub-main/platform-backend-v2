import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, union
from typing import List, Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.models.group import Group, GroupStudent
from app.models.staff_profile import StaffProfile
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.dependencies import get_current_user, require_admin
from app.utils.auth import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("", response_model=List[UserOut])
async def list_users(
    role: Optional[UserRole] = Query(None),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    student_status: Optional[str] = Query(None),
    in_group: Optional[bool] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(User)
    if role:
        q = q.where(User.role == role)
    if search:
        q = q.where(User.full_name.ilike(f"%{search}%"))
    if is_active is not None:
        q = q.where(User.is_active == is_active)
    if student_status is not None:
        q = q.where(User.student_status == student_status)
    if in_group is True:
        q = q.where(User.id.in_(select(GroupStudent.student_id).distinct()))
    elif in_group is False:
        q = q.where(User.id.not_in(select(GroupStudent.student_id).distinct()))
    if branch_id:
        branch_uuid = uuid.UUID(branch_id)
        if role == UserRole.student:
            q = q.where(
                User.id.in_(
                    select(GroupStudent.student_id)
                    .join(Group, Group.id == GroupStudent.group_id)
                    .where(Group.branch_id == branch_uuid)
                )
            )
        elif role == UserRole.teacher:
            q = q.where(
                User.id.in_(
                    select(Group.teacher_id).where(Group.branch_id == branch_uuid)
                )
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
            q = q.where(User.id.in_(select(combined.c.id)))
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.execute(select(User).where(User.phone == data.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Phone already registered")
    user = User(**data.model_dump(exclude={"password"}), password_hash=hash_password(data.password))
    if data.role == UserRole.student:
        user.student_status = "active"
    db.add(user)
    await db.flush()  # get user.id before commit

    # Auto-create staff profile for teacher/staff roles
    if data.role in (UserRole.teacher, UserRole.staff):
        profile = StaffProfile(user_id=user.id)
        db.add(profile)

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
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
