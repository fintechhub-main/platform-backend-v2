import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from typing import List

from app.database import get_db
from app.models.permission import RolePermission, RoleBranchPermission
from app.schemas.permission import RolePermissionCreate, RolePermissionUpdate, RolePermissionOut, RolePermissionsMatrix, RoleBranchPermCreate, RoleBranchPermOut, BranchPermMatrix
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/permissions", tags=["permissions"])

DEFAULT_ROLES = ['superadmin', 'admin', 'teacher', 'staff', 'student']
DEFAULT_PAGES = [
    'dashboard', 'students', 'groups', 'courses', 'attendance',
    'payments', 'fines', 'vacancies', 'certificates', 'rooms',
    'staff', 'crm', 'reports', 'settings',
]


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
