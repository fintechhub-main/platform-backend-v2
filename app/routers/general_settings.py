from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.general_settings import GeneralSettings

router = APIRouter(prefix="/general-settings", tags=["general-settings"])


class GeneralSettingsOut(BaseModel):
    platform_name: Optional[str] = "EduPlatform Pro"
    language: Optional[str] = "uz"
    timezone: Optional[str] = "Asia/Tashkent"
    currency: Optional[str] = "UZS"
    work_start: Optional[str] = "08:00"
    work_end: Optional[str] = "20:00"
    academic_year_start: Optional[str] = "09"
    academic_year_end: Optional[str] = "06"
    work_days: Optional[str] = "1,2,3,4,5,6"


class GeneralSettingsUpdate(BaseModel):
    platform_name: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    work_start: Optional[str] = None
    work_end: Optional[str] = None
    academic_year_start: Optional[str] = None
    academic_year_end: Optional[str] = None
    work_days: Optional[str] = None


@router.get("")
async def get_general_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(GeneralSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        return GeneralSettingsOut().model_dump()
    return {
        "platform_name":       row.platform_name or "EduPlatform Pro",
        "language":            row.language or "uz",
        "timezone":            row.timezone or "Asia/Tashkent",
        "currency":            row.currency or "UZS",
        "work_start":          row.work_start or "08:00",
        "work_end":            row.work_end or "20:00",
        "academic_year_start": row.academic_year_start or "09",
        "academic_year_end":   row.academic_year_end or "06",
        "work_days":           row.work_days or "1,2,3,4,5,6",
    }


@router.patch("")
async def update_general_settings(
    data: GeneralSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(GeneralSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        row = GeneralSettings()
        db.add(row)

    for field, val in data.model_dump(exclude_none=True).items():
        setattr(row, field, val)

    await db.commit()
    return {"ok": True}
