import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from typing import List

from app.database import get_db
from app.models.permission import RolePermission, RoleBranchPermission, CustomRole
from app.schemas.permission import (
    RolePermissionCreate, RolePermissionUpdate, RolePermissionOut,
    RolePermissionsMatrix, RoleBranchPermCreate, RoleBranchPermOut,
    BranchPermMatrix, CustomRoleCreate, CustomRoleOut,
)
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/permissions", tags=["permissions"])

DEFAULT_ROLES = ['superadmin', 'admin', 'manager', 'teacher', 'cashier', 'staff', 'student']
DEFAULT_PAGES = [
    'dashboard', 'students', 'teachers', 'groups', 'courses', 'attendance', 'grades',
    'payments', 'fines', 'vacancies', 'certificates', 'rooms', 'coins',
    'crm', 'events', 'assistant-teacher', 'practicum',
    'exams', 'homework', 'reports', 'blog', 'notifications',
    'logs', 'ai-teacher', 'resume', 'my-lessons', 'users', 'settings', 'bookings',
]


@router.get("/my")
async def my_permissions(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the permission matrix for the currently logged-in user's role."""
    role = str(current_user.role.value if hasattr(current_user.role, "value") else current_user.role)

    if role == "superadmin":
        return {page: {"can_view": True, "can_create": True, "can_update": True, "can_delete": True} for page in DEFAULT_PAGES}

    result = await db.execute(select(RolePermission).where(RolePermission.role == role))
    saved = {p.page_key: p for p in result.scalars().all()}

    out = {}
    for page in DEFAULT_PAGES:
        if page in saved:
            p = saved[page]
            out[page] = {"can_view": p.can_view, "can_create": p.can_create, "can_update": p.can_update, "can_delete": p.can_delete}
        elif role == "admin":
            out[page] = {"can_view": True, "can_create": True, "can_update": True, "can_delete": False}
        else:
            out[page] = {"can_view": False, "can_create": False, "can_update": False, "can_delete": False}
    return out


@router.get("/matrix", response_model=RolePermissionsMatrix)
async def get_matrix(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(RolePermission))
    perms = result.scalars().all()

    # Build matrix with defaults
    matrix = {}
    for role in DEFAULT_ROLES:
        matrix[role] = {}
        for page in DEFAULT_PAGES:
            is_super = role == 'superadmin'
            is_admin = role == 'admin'
            matrix[role][page] = {
                "can_view": is_super or is_admin,
                "can_create": is_super or is_admin,
                "can_update": is_super or is_admin,
                "can_delete": is_super,
            }

    # Override with saved permissions
    for p in perms:
        if p.role not in matrix:
            matrix[p.role] = {}
        matrix[p.role][p.page_key] = {
            "can_view": p.can_view,
            "can_create": p.can_create,
            "can_update": p.can_update,
            "can_delete": p.can_delete,
        }

    return RolePermissionsMatrix(matrix=matrix)


@router.post("/bulk", response_model=List[RolePermissionOut])
async def save_role_permissions(
    items: List[RolePermissionCreate],
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    results = []
    for item in items:
        existing = await db.execute(
            select(RolePermission).where(
                and_(RolePermission.role == item.role, RolePermission.page_key == item.page_key)
            )
        )
        perm = existing.scalar_one_or_none()
        if perm:
            perm.can_view = item.can_view
            perm.can_create = item.can_create
            perm.can_update = item.can_update
            perm.can_delete = item.can_delete
        else:
            perm = RolePermission(**item.model_dump())
            db.add(perm)
        results.append(perm)
    await db.commit()
    for r in results:
        await db.refresh(r)
    return results


@router.get("/branch-matrix", response_model=BranchPermMatrix)
async def get_branch_matrix(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(RoleBranchPermission).where(RoleBranchPermission.allowed == True))
    perms = result.scalars().all()
    matrix = {}
    for p in perms:
        if p.role not in matrix:
            matrix[p.role] = []
        matrix[p.role].append(str(p.branch_id))
    return BranchPermMatrix(matrix=matrix)


@router.get("/roles", response_model=List[CustomRoleOut])
async def get_roles(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    roles = (await db.execute(select(CustomRole).order_by(CustomRole.is_system.desc(), CustomRole.key))).scalars().all()
    return [CustomRoleOut(key=r.key, label=r.label, color=r.color, is_system=r.is_system) for r in roles]


@router.post("/roles", response_model=CustomRoleOut)
async def create_role(item: CustomRoleCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.get(CustomRole, item.key)
    if existing:
        raise HTTPException(400, "Bu kalit allaqachon mavjud")
    role = CustomRole(key=item.key, label=item.label, color=item.color, is_system=False)
    db.add(role)
    await db.commit()
    return CustomRoleOut(key=role.key, label=role.label, color=role.color, is_system=False)


@router.delete("/roles/{key}")
async def delete_role(key: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    role = await db.get(CustomRole, key)
    if role and role.is_system:
        raise HTTPException(400, "Tizim rolini o'chirib bo'lmaydi")
    if role:
        await db.delete(role)
    await db.execute(delete(RolePermission).where(RolePermission.role == key))
    await db.commit()
    return {"deleted": key}


@router.post("/branch-bulk")
async def save_branch_permissions(
    items: List[RoleBranchPermCreate],
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    roles_in_request = list({item.role for item in items})
    for role in roles_in_request:
        await db.execute(delete(RoleBranchPermission).where(RoleBranchPermission.role == role))
    for item in items:
        if item.allowed:
            db.add(RoleBranchPermission(**item.model_dump()))
    await db.commit()
    return {"saved": len([i for i in items if i.allowed])}
