import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.vacancy import Vacancy, VacancyApplicant
from app.schemas.vacancy import (
    VacancyCreate, VacancyUpdate, VacancyOut,
    ApplicantCreate, ApplicantUpdate, ApplicantOut,
)
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


@router.get("", response_model=List[VacancyOut])
async def list_vacancies(
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(Vacancy)
    if is_active is not None:
        q = q.where(Vacancy.is_active == is_active)
    result = await db.execute(q)
    vacancies = result.scalars().all()
    # attach applicant counts
    counts_result = await db.execute(
        select(VacancyApplicant.vacancy_id, func.count().label("cnt"))
        .group_by(VacancyApplicant.vacancy_id)
    )
    counts = {row.vacancy_id: row.cnt for row in counts_result}
    out = []
    for v in vacancies:
        vo = VacancyOut.model_validate(v)
        vo.applicant_count = counts.get(v.id, 0)
        out.append(vo)
    return out


@router.post("", response_model=VacancyOut, status_code=201)
async def create_vacancy(data: VacancyCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    vacancy = Vacancy(**data.model_dump())
    db.add(vacancy)
    await db.commit()
    await db.refresh(vacancy)
    return vacancy


@router.patch("/{vacancy_id}", response_model=VacancyOut)
async def update_vacancy(vacancy_id: uuid.UUID, data: VacancyUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Vacancy).where(Vacancy.id == vacancy_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Not found")
    for k, val in data.model_dump(exclude_none=True).items():
        setattr(v, k, val)
    await db.commit()
    await db.refresh(v)
    return v


@router.delete("/{vacancy_id}", status_code=204)
async def delete_vacancy(vacancy_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Vacancy).where(Vacancy.id == vacancy_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Not found")
    await db.delete(v)
    await db.commit()


# ── Applicants ────────────────────────────────────────────────────────────────

@router.get("/{vacancy_id}/applicants", response_model=List[ApplicantOut])
async def list_applicants(vacancy_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(VacancyApplicant).where(VacancyApplicant.vacancy_id == vacancy_id)
    )
    return result.scalars().all()


@router.post("/applicants", response_model=ApplicantOut, status_code=201)
async def create_applicant(data: ApplicantCreate, db: AsyncSession = Depends(get_db)):
    applicant = VacancyApplicant(**data.model_dump())
    db.add(applicant)
    await db.commit()
    await db.refresh(applicant)
    return applicant


@router.patch("/applicants/{applicant_id}", response_model=ApplicantOut)
async def update_applicant(applicant_id: uuid.UUID, data: ApplicantUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(VacancyApplicant).where(VacancyApplicant.id == applicant_id))
    a = result.scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(a, k, v)
    await db.commit()
    await db.refresh(a)
    return a
