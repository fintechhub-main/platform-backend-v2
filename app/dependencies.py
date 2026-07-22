import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database import get_db
from app.utils.auth import decode_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") == "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    tv = payload.get("tv")
    if tv is not None and tv != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been invalidated")
    return user


def require_roles(*roles: str):
    async def checker(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return current_user
    return checker


require_admin              = require_roles("admin", "superadmin")
require_admin_or_teacher   = require_roles("admin", "superadmin", "teacher")
require_admin_or_manager   = require_roles("admin", "superadmin", "manager")
require_admin_or_cashier   = require_roles("admin", "superadmin", "cashier")
require_staff_roles        = require_roles("admin", "superadmin", "manager", "teacher", "cashier", "staff", "assistant_teacher")


def _get_role_str(user) -> str:
    return str(user.role.value if hasattr(user.role, "value") else user.role)


# O'z guruhlari bilan cheklanadigan rollar (data scoping)
TEACHER_ROLES = ("teacher", "assistant_teacher")


async def check_permission(page_key: str, action: str, current_user, db: AsyncSession) -> None:
    """
    Shared RBAC check — raises 403 if not allowed, returns None if allowed.
    superadmin bypasses; admin defaults to full access except delete when no DB row.
    Used by require_permission() and by ad-hoc checks where the page_key is dynamic.
    """
    role = _get_role_str(current_user)

    if role == "superadmin":
        return

    from app.models.permission import RolePermission

    result = await db.execute(
        select(RolePermission).where(
            and_(RolePermission.role == role, RolePermission.page_key == page_key)
        )
    )
    perm = result.scalar_one_or_none()

    if perm is None:
        # admin defaults: full access except delete
        if role == "admin" and action != "delete":
            return
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    allowed = {
        "view":   perm.can_view,
        "create": perm.can_create,
        "update": perm.can_update,
        "delete": perm.can_delete,
    }.get(action, False)

    if not allowed:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")


def require_permission(page_key: str, action: str = "view"):
    """
    Dynamic RBAC: only superadmin bypasses unconditionally.
    admin defaults to full access when no DB row exists (can_delete excluded).
    All other roles require an explicit row in role_permissions.
    """
    async def checker(
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        await check_permission(page_key, action, current_user, db)
        return current_user
    return checker


async def teacher_owned_group_ids(current_user, db: AsyncSession):
    """
    O'qituvchi (teacher/assistant_teacher) uchun — o'zi biriktirilgan guruh id lari ro'yxati.
    Boshqa rollar uchun None qaytaradi (cheklov yo'q).
    """
    if _get_role_str(current_user) not in TEACHER_ROLES:
        return None
    from app.models.group import Group
    res = await db.execute(select(Group.id).where(Group.teacher_id == current_user.id))
    return list(res.scalars().all())


async def assert_teacher_owns_group(group_id, current_user, db: AsyncSession) -> None:
    """
    O'qituvchi bo'lsa — group_id o'ziga tegishli ekanini tekshiradi, aks holda 403.
    Boshqa rollar uchun hech narsa qilmaydi.
    """
    if _get_role_str(current_user) not in TEACHER_ROLES:
        return
    from app.models.group import Group
    res = await db.execute(select(Group.teacher_id).where(Group.id == group_id))
    tid = res.scalar_one_or_none()
    if tid is None or tid != current_user.id:
        raise HTTPException(status_code=403, detail="Bu guruh sizga tegishli emas")


def is_student(user) -> bool:
    """Foydalanuvchi o'quvchimi (ma'lumotni o'zi bilan cheklash uchun)."""
    return _get_role_str(user) == "student"


async def teacher_course_ids(current_user, db: AsyncSession):
    """
    O'qituvchi o'qitadigan kurslar (o'z guruhlari orqali) id lari ro'yxati.
    Boshqa rollar uchun None qaytaradi (cheklov yo'q).
    """
    if _get_role_str(current_user) not in TEACHER_ROLES:
        return None
    from app.models.group import Group
    res = await db.execute(
        select(Group.course_id).where(Group.teacher_id == current_user.id).distinct()
    )
    return [c for c in res.scalars().all() if c is not None]
