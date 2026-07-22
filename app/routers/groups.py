import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional

from app.database import get_db
from app.models.group import Group, GroupStudent, GroupStatus
from app.models.user import User
from app.schemas.group import GroupCreate, GroupUpdate, GroupOut, GroupDetailOut, GroupSlim
from app.schemas.user import UserOut
from app.dependencies import (
    get_current_user, require_permission,
    teacher_owned_group_ids, assert_teacher_owns_group, is_student,
)
from app.utils.attendance_generator import generate_attendance_for_group
from app.models.telegram_log import TelegramLog
from app.utils.attendance_telegram import send_group_attendance
from app.config import settings
import secrets
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/my", response_model=List[GroupOut])
async def my_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(Group)
        .join(GroupStudent, GroupStudent.group_id == Group.id)
        .options(selectinload(Group.teacher), selectinload(Group.course))
        .where(GroupStudent.student_id == current_user.id)
        .order_by(Group.start_date.desc())
    )
    result = await db.execute(q)
    groups = result.scalars().all()
    out = []
    for g in groups:
        data = GroupOut.model_validate(g)
        data.teacher_name = g.teacher.full_name if g.teacher else None
        data.course_title = g.course.title if g.course else None
        out.append(data)
    return out


@router.get("", response_model=List[GroupOut])
async def list_groups(
    course_id: Optional[uuid.UUID] = Query(None),
    teacher_id: Optional[uuid.UUID] = Query(None),
    student_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0, limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("groups", "view")),
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
    # O'qituvchi bo'lsa — faqat o'z guruhlari
    owned = await teacher_owned_group_ids(current_user, db)
    if owned is not None:
        q = q.where(Group.id.in_(owned))
    # O'quvchi bo'lsa — faqat o'zi a'zo bo'lgan guruhlar
    if is_student(current_user):
        q = q.where(Group.id.in_(
            select(GroupStudent.group_id).where(GroupStudent.student_id == current_user.id)))
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
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("groups", "create"))):
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
    current_user: User = Depends(require_permission("groups", "view")),
):
    q = (
        select(User, GroupStudent.group_id)
        .join(GroupStudent, GroupStudent.student_id == User.id)
        .where(GroupStudent.is_frozen == True)
    )
    if branch_id:
        q = q.join(Group, Group.id == GroupStudent.group_id).where(Group.branch_id == uuid.UUID(branch_id))
    # O'qituvchi bo'lsa — faqat o'z guruhlaridagi muzlatilgan talabalar
    owned = await teacher_owned_group_ids(current_user, db)
    if owned is not None:
        q = q.where(GroupStudent.group_id.in_(owned))
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
    current_user: User = Depends(require_permission("groups", "view")),
):
    """Lightweight group list — only fields needed for filter dropdowns and student mapping."""
    q = select(Group).options(joinedload(Group.teacher))
    if branch_id:
        q = q.where(Group.branch_id == uuid.UUID(branch_id))
    if course_id:
        q = q.where(Group.course_id == course_id)
    if status:
        q = q.where(Group.status == status)
    # O'qituvchi bo'lsa — faqat o'z guruhlari
    owned = await teacher_owned_group_ids(current_user, db)
    if owned is not None:
        q = q.where(Group.id.in_(owned))
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
async def get_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "view"))):
    from datetime import date
    await assert_teacher_owns_group(group_id, current_user, db)
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
async def update_group(group_id: uuid.UUID, data: GroupUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "update"))):
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(group, k, v)
    await db.commit()
    await db.refresh(group)
    return group


@router.patch("/{group_id}/status", response_model=GroupOut)
async def update_group_status(
    group_id: uuid.UUID,
    status: GroupStatus = Query(...),
    db: AsyncSession = Depends(get_db),
    # groups:view + assert_teacher_owns_group yetarli — o'z guruhini yuritayotgan
    # ustoz uni bitirdi/to'xtatdi deb belgilashi kerak, lekin narx/jadval kabi
    # boshqa maydonlarni tahrirlay olmasligi kerak (buning uchun to'liq
    # "update" huquqi kerak, PATCH /groups/{id} orqali).
    current_user: User = Depends(require_permission("groups", "view")),
):
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    group.status = status
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "delete"))):
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    await db.delete(group)
    await db.commit()


@router.get("/{group_id}/students")
async def group_students(
    group_id: uuid.UUID,
    is_frozen: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("groups", "view")),
):
    await assert_teacher_owns_group(group_id, current_user, db)
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
async def freeze_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "update"))):
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(404, "Not found")
    gs.is_frozen = True
    await db.commit()
    return {"ok": True}


@router.patch("/{group_id}/students/{student_id}/unfreeze", status_code=200)
async def unfreeze_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "update"))):
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(404, "Not found")
    gs.is_frozen = False
    await db.commit()
    return {"ok": True}


@router.post("/{group_id}/students/{student_id}", status_code=201)
async def add_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "update"))):
    from datetime import date
    await assert_teacher_owns_group(group_id, current_user, db)
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
async def remove_student(group_id: uuid.UUID, student_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("groups", "update"))):
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(
        select(GroupStudent).where(GroupStudent.group_id == group_id, GroupStudent.student_id == student_id)
    )
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(404, "Not found")
    await db.delete(gs)
    await db.commit()


# ── O'quvchi ro'yxatdan o'tish havolasi (Telegram bot orqali) ─────────────────

INVITE_LINK_TTL = timedelta(hours=6)


def _invite_url(token: str) -> str:
    return "https://t.me/{}?start={}".format(settings.TEACHER_BOT_USERNAME, token)


def _invite_out(group: Group) -> dict:
    return {
        "token": group.invite_token,
        "url": _invite_url(group.invite_token),
        "expires_at": group.invite_token_expires_at.isoformat() if group.invite_token_expires_at else None,
    }


@router.get("/{group_id}/invite-link")
async def get_invite_link(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    # groups:view + assert_teacher_owns_group yetarli — ustoz o'z guruhi uchun
    # havola olishi kerak, lekin guruh sozlamalarini tahrirlay olmasligi mumkin.
    current_user: User = Depends(require_permission("groups", "view")),
):
    """Guruhga Telegram bot orqali yozilish havolasi. Yo'q yoki muddati o'tgan bo'lsa yangisi yaratiladi.

    Havola yaratilgan/yangilangan paytdan boshlab 6 soat amal qiladi — shundan
    keyin bot uni tanimay qo'yadi, admin qayta ochib yangisini olishi kerak.
    """
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    now = datetime.now(timezone.utc)
    expired = not group.invite_token_expires_at or group.invite_token_expires_at <= now
    if not group.invite_token or expired:
        group.invite_token = secrets.token_urlsafe(12)
        group.invite_token_expires_at = now + INVITE_LINK_TTL
        await db.commit()
        await db.refresh(group)
    return _invite_out(group)


@router.post("/{group_id}/invite-link/regenerate")
async def regenerate_invite_link(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("groups", "view")),
):
    """Eski havolani bekor qilib, yangisini yaratadi (masalan, havola noo'rin joyga tarqalgan bo'lsa).

    Yangi havola ham generatsiya qilingan paytdan 6 soat amal qiladi.
    """
    await assert_teacher_owns_group(group_id, current_user, db)
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    group.invite_token = secrets.token_urlsafe(12)
    group.invite_token_expires_at = datetime.now(timezone.utc) + INVITE_LINK_TTL
    await db.commit()
    await db.refresh(group)
    return _invite_out(group)


# ── Telegram davomat loglari ──────────────────────────────────────────────────

@router.get("/{group_id}/telegram-logs")
async def group_telegram_logs(
    group_id: uuid.UUID,
    limit: int = Query(30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("groups", "view")),
):
    await assert_teacher_owns_group(group_id, current_user, db)
    rows = (await db.execute(
        select(TelegramLog)
        .where(TelegramLog.group_id == group_id)
        .order_by(TelegramLog.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {
            "id": str(l.id),
            "date": l.log_date.isoformat() if l.log_date else None,
            "status": l.status,
            "error": l.error,
            "text": l.text,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in rows
    ]


@router.post("/{group_id}/send-attendance")
async def send_group_attendance_now(
    group_id: uuid.UUID,
    date: Optional[str] = Query(None),  # YYYY-MM-DD, default: kecha
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("groups", "view")),
):
    from datetime import date as date_cls, timedelta
    await assert_teacher_owns_group(group_id, current_user, db)
    res = await db.execute(select(Group).where(Group.id == group_id))
    group = res.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")
    target = date_cls.fromisoformat(date) if date else (date_cls.today() - timedelta(days=1))
    status = await send_group_attendance(db, group, target, force=True)
    if status is None:
        return {"status": "skipped", "detail": "Bu kunga davomat yozuvi yo'q", "date": target.isoformat()}
    return {"status": status, "date": target.isoformat()}
