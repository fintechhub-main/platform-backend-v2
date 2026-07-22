import uuid
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.notification import Notification
from app.models.user import User
from app.models.group import Group, GroupStudent
from app.services.notify import notify_users_bulk

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationCreate(BaseModel):
    user_id: str
    title: str
    body: str
    notification_type: str = "system"
    priority: str = "normal"
    extra_data: Optional[dict] = None



class SendBulkIn(BaseModel):
    title: str
    body: str
    notification_type: str = "system"
    group_id: Optional[str] = None
    branch_id: Optional[str] = None
    user_id: Optional[str] = None


def _out(n: Notification):
    return {
        "id": str(n.id),
        "title": n.title,
        "body": n.body,
        "notification_type": n.notification_type,
        "priority": n.priority,
        "extra_data": n.extra_data or {},
        "is_read": n.is_read,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat(),
    }


@router.get("")
async def list_notifications(
    is_read: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Notification).where(Notification.user_id == current_user.id)
    if is_read is not None:
        q = q.where(Notification.is_read == is_read)
    q = q.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()
    return [_out(n) for n in items]


@router.get("/unread-count")
async def unread_count(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count()).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    return {"count": result.scalar() or 0}


@router.post("/mark-all-read")
async def mark_all_read(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True, read_at=now)
    )
    await db.commit()
    return {"ok": True}


@router.patch("/{notification_id}/mark-read")
async def mark_read(
    notification_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Topilmadi")
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
    return _out(notif)


@router.post("")
async def create_notification(
    data: NotificationCreate,
    _=Depends(require_permission("settings", "create")),
    db: AsyncSession = Depends(get_db),
):
    notif = Notification(
        user_id=uuid.UUID(data.user_id),
        title=data.title,
        body=data.body,
        notification_type=data.notification_type,
        priority=data.priority,
        extra_data=data.extra_data or {},
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return _out(notif)


@router.post("/send-bulk")
async def send_bulk_notification(
    data: SendBulkIn,
    _=Depends(require_permission("settings", "create")),
    db: AsyncSession = Depends(get_db),
):
    """Admin sends push notification to a group, branch, or specific user."""
    import uuid as _uuid
    user_ids = []
    if data.user_id:
        user_ids = [_uuid.UUID(data.user_id)]
    elif data.group_id:
        result = await db.execute(
            select(GroupStudent.student_id).where(GroupStudent.group_id == _uuid.UUID(data.group_id))
        )
        user_ids = [r[0] for r in result.all()]
    elif data.branch_id:
        result = await db.execute(
            select(User.id).where(
                User.branch_id == _uuid.UUID(data.branch_id),
                User.role == "student",
                User.is_active == True,
            )
        )
        user_ids = [r[0] for r in result.all()]

    if not user_ids:
        return {"sent": 0}

    await notify_users_bulk(
        db, user_ids, title=data.title, body=data.body,
        notification_type=data.notification_type,
    )
    await db.commit()
    return {"sent": len(user_ids)}
