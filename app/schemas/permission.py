import uuid
from pydantic import BaseModel
from typing import List, Optional, Dict


class RolePermissionCreate(BaseModel):
    role: str
    page_key: str
    can_view: bool = True
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False


class RolePermissionUpdate(BaseModel):
    can_view: Optional[bool] = None
    can_create: Optional[bool] = None
    can_update: Optional[bool] = None
    can_delete: Optional[bool] = None


class RolePermissionOut(BaseModel):
    id: uuid.UUID
    role: str
    page_key: str
    can_view: bool
    can_create: bool
    can_update: bool
    can_delete: bool
    model_config = {"from_attributes": True}


class RolePermissionsMatrix(BaseModel):
    # {role: {page_key: {can_view, can_create, ...}}}
    matrix: Dict[str, Dict[str, dict]]
