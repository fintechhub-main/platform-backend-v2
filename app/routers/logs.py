import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_

from app.database import get_db
from app.dependencies import get_current_user
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
async def list_logs(
    action: Optional[str] = Query(None),
    user_name: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(AuditLog).order_by(desc(AuditLog.created_at))
    if action:
        q = q.where(AuditLog.action == action)
    if user_name:
        q = q.where(AuditLog.user_name == user_name)
    if branch_id:
        q = q.where(AuditLog.branch_id == uuid.UUID(branch_id))
    if date_from:
        q = q.where(AuditLog.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        q = q.where(AuditLog.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
    if search:
        like = f"%{search}%"
        q = q.where(or_(
            AuditLog.target.ilike(like),
            AuditLog.detail.ilike(like),
            AuditLog.user_name.ilike(like),
        ))
    result = await db.execute(q.offset(skip).limit(limit))
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "user": {
                "name": r.user_name or "Noma'lum",
                "role": r.user_role or "",
                "avatar": "".join(p[0].upper() for p in (r.user_name or "?").split()[:2]),
            },
            "action": r.action,
            "target": r.target or "",
            "detail": r.detail or "",
            "ip": r.ip or "",
            "time": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for r in rows
    ]


@router.post("")
async def create_log(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    log = AuditLog(
        user_id=current_user.id,
        user_name=current_user.full_name,
        user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        action=body.get("action", "unknown"),
        target=body.get("target"),
        detail=body.get("detail"),
        ip=body.get("ip"),
        branch_id=uuid.UUID(body["branch_id"]) if body.get("branch_id") else None,
    )
    db.add(log)
    await db.commit()
    return {"ok": True}
