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
        role = _get_role_str(current_user)

        if role == "superadmin":
            return current_user

        from app.models.permission import RolePermission

        result = await db.execute(
            select(RolePermission).where(
                and_(RolePermission.role == role, RolePermission.page_key == page_key)
            )
        )
        perm = result.scalar_one_or_none()

        if perm is None:
            # admin defaults: full access except delete
            if role == "admin":
                if action == "delete":
                    raise HTTPException(status_code=403, detail="Ruxsat yo'q")
                return current_user
            raise HTTPException(status_code=403, detail="Ruxsat yo'q")

        allowed = {
            "view":   perm.can_view,
            "create": perm.can_create,
            "update": perm.can_update,
            "delete": perm.can_delete,
        }.get(action, False)

        if not allowed:
            raise HTTPException(status_code=403, detail="Ruxsat yo'q")
        return current_user
    return checker
