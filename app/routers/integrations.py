from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import require_permission
from app.models.integration_settings import IntegrationSettings

router = APIRouter(prefix="/integrations", tags=["integrations"])

SENSITIVE = {"api_key", "api_secret", "password", "bot_token"}


def _mask(val: Optional[str]) -> Optional[str]:
    return "***" if val else None


class IntegrationOut(BaseModel):
    key: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    endpoint: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    bot_token: Optional[str] = None
    is_active: bool = False

    model_config = {"from_attributes": True}


class IntegrationUpdate(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    endpoint: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    bot_token: Optional[str] = None
    is_active: Optional[bool] = None


INTEGRATION_KEYS = ["telegram", "eskiz", "playmobile", "firebase", "amocrm", "bitrix"]


@router.get("")
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("settings", "view")),
):
    result = await db.execute(select(IntegrationSettings))
    rows = {r.key: r for r in result.scalars().all()}

    out = []
    for key in INTEGRATION_KEYS:
        row = rows.get(key)
        if row:
            out.append({
                "key": key,
                "api_key":    _mask(row.api_key),
                "api_secret": _mask(row.api_secret),
                "endpoint":   row.endpoint,
                "login":      row.login,
                "password":   _mask(row.password),
                "bot_token":  _mask(row.bot_token),
                "is_active":  row.is_active,
            })
        else:
            out.append({"key": key, "is_active": False})
    return out


@router.patch("/{key}")
async def update_integration(
    key: str,
    data: IntegrationUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("settings", "update")),
):
    if key not in INTEGRATION_KEYS:
        from fastapi import HTTPException
        raise HTTPException(404, "Integration not found")

    result = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.key == key)
    )
    row = result.scalar_one_or_none()

    if not row:
        row = IntegrationSettings(key=key)
        db.add(row)

    update = data.model_dump(exclude_none=True)
    for field, val in update.items():
        if field in SENSITIVE and val == "***":
            continue
        setattr(row, field, val)

    # Mark active if any credential is set
    if data.is_active is None:
        has_cred = any([row.api_key, row.bot_token, row.login])
        row.is_active = has_cred

    await db.commit()
    return {"ok": True}
