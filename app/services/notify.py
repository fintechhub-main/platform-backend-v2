import uuid
import asyncio
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.notification import Notification
from app.models.user import User
from app.services.fcm import send_push, send_push_multicast

logger = logging.getLogger(__name__)


async def notify_user(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    title: str,
    body: str,
    notification_type: str = "system",
    data: Optional[dict] = None,
):
    """Save notification to DB and send FCM push."""
    try:
        uid = uuid.UUID(str(user_id))
        notif = Notification(
            user_id=uid,
            title=title,
            body=body,
            notification_type=notification_type,
            extra_data=data or {},
        )
        db.add(notif)

        result = await db.execute(select(User.fcm_token).where(User.id == uid))
        token = result.scalar_one_or_none()
        await db.flush()

        if token:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, send_push, token, title, body, data or {})
    except Exception as e:
        logger.error(f"notify_user error: {e}")


async def notify_users_bulk(
    db: AsyncSession,
    user_ids: list[uuid.UUID | str],
    title: str,
    body: str,
    notification_type: str = "system",
    data: Optional[dict] = None,
):
    """Notify multiple users: save to DB + FCM multicast."""
    if not user_ids:
        return
    try:
        uids = [uuid.UUID(str(u)) for u in user_ids]
        for uid in uids:
            db.add(Notification(
                user_id=uid,
                title=title,
                body=body,
                notification_type=notification_type,
                extra_data=data or {},
            ))

        result = await db.execute(
            select(User.fcm_token).where(User.id.in_(uids), User.fcm_token.isnot(None))
        )
        tokens = [row[0] for row in result.all() if row[0]]
        await db.flush()

        if tokens:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, send_push_multicast, tokens, title, body, data or {})
    except Exception as e:
        logger.error(f"notify_users_bulk error: {e}")
