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
    # Notification settings
    notif_email: Optional[bool] = True
    notif_sms: Optional[bool] = False
    notif_telegram: Optional[bool] = True
    notif_payment: Optional[bool] = True
    notif_attendance: Optional[bool] = True
    notif_exams: Optional[bool] = False
    # Payment settings
    payment_methods: Optional[str] = "cash,card"
    late_fee_percent: Optional[str] = "0"
    payment_day: Optional[str] = "1"


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
    # Notification settings
    notif_email: Optional[bool] = None
    notif_sms: Optional[bool] = None
    notif_telegram: Optional[bool] = None
    notif_payment: Optional[bool] = None
    notif_attendance: Optional[bool] = None
    notif_exams: Optional[bool] = None
    # Payment settings
    payment_methods: Optional[str] = None
    late_fee_percent: Optional[str] = None
    payment_day: Optional[str] = None


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
        # Notification settings
        "notif_email":         row.notif_email if row.notif_email is not None else True,
        "notif_sms":           row.notif_sms if row.notif_sms is not None else False,
        "notif_telegram":      row.notif_telegram if row.notif_telegram is not None else True,
        "notif_payment":       row.notif_payment if row.notif_payment is not None else True,
        "notif_attendance":    row.notif_attendance if row.notif_attendance is not None else True,
        "notif_exams":         row.notif_exams if row.notif_exams is not None else False,
        # Payment settings
        "payment_methods":     row.payment_methods or "cash,card",
        "late_fee_percent":    row.late_fee_percent or "0",
        "payment_day":         row.payment_day or "1",
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
