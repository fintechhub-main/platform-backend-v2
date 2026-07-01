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
    'logs', 'ai-teacher', 'resume', 'my-lessons', 'users', 'settings',
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


@router.get("/roles", response_model=List[CustomRoleOut])
async def get_roles(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    custom = (await db.execute(select(CustomRole))).scalars().all()
    custom_keys = {r.key for r in custom}
    defaults = [
        CustomRoleOut(key=k, label=l, color=c, is_default=True)
        for k, l, c in [
            ("superadmin", "Super Admin", "#7c3aed"),
            ("admin",      "Admin",       "#2563eb"),
            ("manager",    "Menejer",     "#0891b2"),
            ("teacher",    "O'qituvchi",  "#16a34a"),
            ("cashier",    "Kassir",      "#d97706"),
            ("staff",      "Xodim",       "#475569"),
            ("student",    "Talaba",      "#6b7280"),
        ] if k not in custom_keys
    ]
    return defaults + [CustomRoleOut(key=r.key, label=r.label, color=r.color, is_default=False) for r in custom]


@router.post("/roles", response_model=CustomRoleOut)
async def create_role(item: CustomRoleCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    existing = await db.get(CustomRole, item.key)
    if existing:
        raise HTTPException(400, "Bu kalit allaqachon mavjud")
    role = CustomRole(key=item.key, label=item.label, color=item.color)
    db.add(role)
    await db.commit()
    return CustomRoleOut(key=role.key, label=role.label, color=role.color, is_default=False)


@router.delete("/roles/{key}")
async def delete_role(key: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    default_keys = {"superadmin", "admin", "manager", "teacher", "cashier", "staff", "student"}
    if key in default_keys:
        raise HTTPException(400, "Standart rolni o'chirib bo'lmaydi")
    role = await db.get(CustomRole, key)
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
