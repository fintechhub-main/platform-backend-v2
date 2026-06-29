import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database import get_db, AsyncSessionLocal
from app.models.telegram_source import TelegramSource
from app.dependencies import require_admin
from app.utils.telegram_fetcher import _parse_channel_username

router = APIRouter(prefix="/telegram-sources", tags=["telegram-sources"])


class TelegramSourceCreate(BaseModel):
    channel_url: str
    last_message_url: Optional[str] = None
    is_active: bool = True
    branch_id: Optional[uuid.UUID] = None


class TelegramSourceUpdate(BaseModel):
    channel_url: Optional[str] = None
    is_active: Optional[bool] = None
    last_message_id: Optional[int] = None
    branch_id: Optional[uuid.UUID] = None


class TelegramSourceOut(BaseModel):
    id: uuid.UUID
    channel_url: str
    channel_username: str
    last_message_id: int
    last_checked_at: Optional[datetime]
    last_error: Optional[str]
    is_active: bool
    branch_id: Optional[uuid.UUID]
    vacancies_found: int
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=List[TelegramSourceOut])
async def list_sources(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(TelegramSource).order_by(TelegramSource.created_at.desc())
    if branch_id:
        q = q.where(TelegramSource.branch_id == uuid.UUID(branch_id))
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=TelegramSourceOut, status_code=201)
async def create_source(
    data: TelegramSourceCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    username = _parse_channel_username(data.channel_url)

    # Parse last_message_id from the provided URL
    last_id = 0
    if data.last_message_url:
        try:
            last_id = int(data.last_message_url.strip().rstrip('/').split('/')[-1])
        except (ValueError, IndexError):
            last_id = 0

    source = TelegramSource(
        channel_url=data.channel_url.strip().rstrip('/'),
        channel_username=username,
        last_message_id=last_id,
        is_active=data.is_active,
        branch_id=data.branch_id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.patch("/{source_id}", response_model=TelegramSourceOut)
async def update_source(
    source_id: uuid.UUID,
    data: TelegramSourceUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(TelegramSource).where(TelegramSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Not found")

    for k, v in data.model_dump(exclude_none=True).items():
        if k == "channel_url" and v:
            source.channel_username = _parse_channel_username(v)
        setattr(source, k, v)

    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(TelegramSource).where(TelegramSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Not found")
    await db.delete(source)
    await db.commit()


@router.post("/{source_id}/run", status_code=200)
async def run_source_now(
    source_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Manually trigger fetch for one source."""
    result = await db.execute(select(TelegramSource).where(TelegramSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Not found")

    async def _run():
        from app.utils.vacancy_auto_fetch import _process_source
        async with AsyncSessionLocal() as session:
            result2 = await session.execute(
                select(TelegramSource).where(TelegramSource.id == source_id)
            )
            src = result2.scalar_one_or_none()
            if src:
                await _process_source(session, src)

    background_tasks.add_task(_run)
    return {"status": "started", "source_id": str(source_id)}


@router.post("/run-all", status_code=200)
async def run_all_now(
    background_tasks: BackgroundTasks,
    _=Depends(require_admin),
):
    """Manually trigger fetch for all active sources."""
    async def _run():
        from app.utils.vacancy_auto_fetch import run_auto_fetch
        async with AsyncSessionLocal() as session:
            await run_auto_fetch(session)

    background_tasks.add_task(_run)
    return {"status": "started"}
