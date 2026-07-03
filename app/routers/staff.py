import uuid
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.staff_profile import StaffProfile
from app.models.group import Group
from app.schemas.staff import StaffOut, StaffProfileUpdate
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/staff", tags=["staff"])


def _build_out(user: User, profile: StaffProfile) -> dict:
    return {
        "id": profile.id,
        "user_id": user.id,
        "full_name": user.full_name,
        "phone": user.phone,
        "email": user.email,
        "role": str(user.role),
        "status": profile.status.value,
        "specializations": profile.specializations,
        "bio": profile.bio,
        "experience": profile.experience,
        "qualifications": profile.qualifications,
        "rating": profile.rating,
        "monthly_earnings": profile.monthly_earnings,
        "kpi_attendance": profile.kpi_attendance,
        "kpi_results": profile.kpi_results,
        "kpi_loss": profile.kpi_loss,
        "week_schedule": profile.week_schedule,
        "performance_history": profile.performance_history,
        "salary_history": profile.salary_history,
    }


@router.get("", response_model=list[StaffOut])
async def list_staff(
    role: str | None = None,
    status: str | None = None,
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("teachers", "view")),
):
    from app.models.user import UserRole
    from app.models.staff_profile import StaffStatus
    q = (
        select(User, StaffProfile)
        .join(StaffProfile, StaffProfile.user_id == User.id)
    )
    if role:
        q = q.where(User.role == role)
    else:
        q = q.where(User.role.in_([UserRole.teacher, UserRole.assistant_teacher, UserRole.staff]))

    if status:
        q = q.where(StaffProfile.status == StaffStatus(status))

    if branch_id:
        q = q.where(User.branch_id == uuid.UUID(branch_id))

    rows = (await db.execute(q)).all()
    return [StaffOut.model_validate(_build_out(u, p)) for u, p in rows]


@router.get("/{user_id}", response_model=StaffOut)
async def get_staff(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("teachers", "view")),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(User, StaffProfile)
        .join(StaffProfile, StaffProfile.user_id == User.id)
        .where(User.id == user_id)
    )
    row = (await db.execute(q)).one_or_none()
    if not row:
        raise HTTPException(404, "Staff not found")
    return StaffOut.model_validate(_build_out(row[0], row[1]))


@router.patch("/{user_id}", response_model=StaffOut)
async def update_staff(
    user_id: uuid.UUID,
    body: StaffProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("teachers", "update")),
):
    # Only admin or the staff member themselves can update
    q = (
        select(User, StaffProfile)
        .join(StaffProfile, StaffProfile.user_id == User.id)
        .where(User.id == user_id)
    )
    row = (await db.execute(q)).one_or_none()
    if not row:
        raise HTTPException(404, "Staff not found")
    user, profile = row

    data = body.model_dump(exclude_none=True)
    for field in ("specializations", "qualifications", "week_schedule", "performance_history", "salary_history"):
        if field in data and not isinstance(data[field], str):
            data[field] = json.dumps(data[field], ensure_ascii=False)

    if "status" in data:
        from app.models.staff_profile import StaffStatus
        data["status"] = StaffStatus(data["status"])

    for k, v in data.items():
        setattr(profile, k, v)

    await db.commit()
    await db.refresh(profile)
    return StaffOut.model_validate(_build_out(user, profile))
