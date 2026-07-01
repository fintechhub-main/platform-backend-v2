import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.practicum import PracticumTeam, PracticumTask
from app.schemas.practicum import (
    TeamCreate, TeamUpdate, TeamOut,
    TaskCreate, TaskUpdate, TaskOut,
)
from app.dependencies import get_current_user, require_admin, require_admin_or_teacher

router = APIRouter(prefix="/practicum", tags=["practicum"])


# ── Teams ─────────────────────────────────────────────────────────────────────

@router.get("/teams", response_model=List[TeamOut])
async def list_teams(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(PracticumTeam).options(selectinload(PracticumTeam.tasks))
    if branch_id:
        try:
            bid = uuid.UUID(branch_id)
        except ValueError:
            raise HTTPException(400, "Invalid branch_id")
        q = q.where(PracticumTeam.branch_id == bid)
    result = await db.execute(q)
    teams = result.scalars().all()
    return teams


@router.post("/teams", response_model=TeamOut, status_code=201)
async def create_team(
    data: TeamCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    team = PracticumTeam(**data.model_dump())
    db.add(team)
    await db.commit()
    await db.refresh(team)
    # reload with tasks (empty list for new team)
    result = await db.execute(
        select(PracticumTeam)
        .options(selectinload(PracticumTeam.tasks))
        .where(PracticumTeam.id == team.id)
    )
    return result.scalar_one()


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: uuid.UUID,
    data: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(PracticumTeam)
        .options(selectinload(PracticumTeam.tasks))
        .where(PracticumTeam.id == team_id)
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(404, "Team not found")
    for k, val in data.model_dump(exclude_none=True).items():
        setattr(team, k, val)
    await db.commit()
    await db.refresh(team)
    result2 = await db.execute(
        select(PracticumTeam)
        .options(selectinload(PracticumTeam.tasks))
        .where(PracticumTeam.id == team_id)
    )
    return result2.scalar_one()


@router.delete("/teams/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(PracticumTeam).where(PracticumTeam.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(404, "Team not found")
    await db.delete(team)
    await db.commit()


@router.get("/teams/{team_id}/tasks", response_model=List[TaskOut])
async def list_tasks(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(PracticumTask).where(PracticumTask.team_id == team_id)
    )
    return result.scalars().all()


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    task = PracticumTask(**data.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    result = await db.execute(select(PracticumTask).where(PracticumTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    for k, val in data.model_dump(exclude_none=True).items():
        setattr(task, k, val)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    result = await db.execute(select(PracticumTask).where(PracticumTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    await db.delete(task)
    await db.commit()
