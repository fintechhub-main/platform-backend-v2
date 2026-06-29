"""Audit log yozish uchun yagona helper."""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog


async def write_log(
    db: AsyncSession,
    *,
    user,               # get_current_user dan kelgan User ob'ekti
    action: str,        # masalan: "attendance.update", "grade.create"
    target: str = "",   # masalan: "student_id:..., date:2026-06-29"
    detail: str = "",   # batafsil ma'lumot
    ip: str = "",
    branch_id: uuid.UUID | None = None,
):
    log = AuditLog(
        user_id=user.id,
        user_name=user.full_name,
        user_role=user.role.value if hasattr(user.role, "value") else str(user.role),
        action=action,
        target=target,
        detail=detail,
        ip=ip,
        branch_id=branch_id,
    )
    db.add(log)
    await db.flush()  # commit bilan birga saqlanadi
