import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.resume import Resume, ResumeEducation, ResumeWorkExperience, ResumeLeadership

router = APIRouter(prefix="/resume", tags=["resume"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ResumeUpdate(BaseModel):
    summary: Optional[str] = None
    position: Optional[str] = None
    city: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None


class EducationCreate(BaseModel):
    university: str
    location: Optional[str] = None
    degree: Optional[str] = None
    year: Optional[str] = None
    course_work: Optional[List[str]] = None


class WorkExperienceCreate(BaseModel):
    company: str
    location: Optional[str] = None
    position: Optional[str] = None
    duration: Optional[str] = None
    achievements: Optional[List[str]] = None


class LeadershipCreate(BaseModel):
    company: str
    location: Optional[str] = None
    position: Optional[str] = None
    duration: Optional[str] = None
    achievements: Optional[List[str]] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _edu_out(e: ResumeEducation):
    return {"id": str(e.id), "university": e.university, "location": e.location,
            "degree": e.degree, "year": e.year, "course_work": e.course_work or []}

def _work_out(w: ResumeWorkExperience):
    return {"id": str(w.id), "company": w.company, "location": w.location,
            "position": w.position, "duration": w.duration, "achievements": w.achievements or []}

def _lead_out(l: ResumeLeadership):
    return {"id": str(l.id), "company": l.company, "location": l.location,
            "position": l.position, "duration": l.duration, "achievements": l.achievements or []}

def _resume_out(r: Resume):
    return {
        "id": str(r.id),
        "user_id": str(r.user_id),
        "summary": r.summary,
        "position": r.position,
        "city": r.city,
        "linkedin": r.linkedin,
        "github": r.github,
        "skills": r.skills or [],
        "interests": r.interests or [],
        "education": [_edu_out(e) for e in (r.education or [])],
        "work_experience": [_work_out(w) for w in (r.work_experience or [])],
        "leadership": [_lead_out(l) for l in (r.leadership or [])],
        "updated_at": r.updated_at.isoformat(),
    }


async def _load_resume(user_id: uuid.UUID, db: AsyncSession, create_if_missing=False) -> Optional[Resume]:
    result = await db.execute(
        select(Resume)
        .options(
            selectinload(Resume.education),
            selectinload(Resume.work_experience),
            selectinload(Resume.leadership),
        )
        .where(Resume.user_id == user_id)
    )
    resume = result.scalar_one_or_none()
    if not resume and create_if_missing:
        resume = Resume(user_id=user_id)
        db.add(resume)
        await db.commit()
        result2 = await db.execute(
            select(Resume)
            .options(selectinload(Resume.education), selectinload(Resume.work_experience), selectinload(Resume.leadership))
            .where(Resume.user_id == user_id)
        )
        resume = result2.scalar_one()
    return resume


# ── Main resume endpoints ─────────────────────────────────────────────────────

@router.get("/me")
async def get_my_resume(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db, create_if_missing=True)
    return _resume_out(resume)


@router.get("/{user_id}")
async def get_resume_by_user(
    user_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(user_id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    return _resume_out(resume)


@router.put("/me")
async def update_my_resume(
    data: ResumeUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db, create_if_missing=True)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(resume, k, v)
    await db.commit()
    return _resume_out(await _load_resume(current_user.id, db))


# ── Education ─────────────────────────────────────────────────────────────────

@router.post("/me/education", status_code=201)
async def add_education(
    data: EducationCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db, create_if_missing=True)
    edu = ResumeEducation(resume_id=resume.id, **data.model_dump())
    db.add(edu)
    await db.commit()
    await db.refresh(edu)
    return _edu_out(edu)


@router.patch("/me/education/{edu_id}")
async def update_education(
    edu_id: uuid.UUID,
    data: EducationCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    result = await db.execute(select(ResumeEducation).where(ResumeEducation.id == edu_id, ResumeEducation.resume_id == resume.id))
    edu = result.scalar_one_or_none()
    if not edu:
        raise HTTPException(404, "Topilmadi")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(edu, k, v)
    await db.commit()
    await db.refresh(edu)
    return _edu_out(edu)


@router.delete("/me/education/{edu_id}", status_code=204)
async def delete_education(
    edu_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    result = await db.execute(select(ResumeEducation).where(ResumeEducation.id == edu_id, ResumeEducation.resume_id == resume.id))
    edu = result.scalar_one_or_none()
    if not edu:
        raise HTTPException(404, "Topilmadi")
    await db.delete(edu)
    await db.commit()


# ── Work Experience ───────────────────────────────────────────────────────────

@router.post("/me/work-experience", status_code=201)
async def add_work_experience(
    data: WorkExperienceCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db, create_if_missing=True)
    work = ResumeWorkExperience(resume_id=resume.id, **data.model_dump())
    db.add(work)
    await db.commit()
    await db.refresh(work)
    return _work_out(work)


@router.patch("/me/work-experience/{work_id}")
async def update_work_experience(
    work_id: uuid.UUID,
    data: WorkExperienceCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    result = await db.execute(select(ResumeWorkExperience).where(ResumeWorkExperience.id == work_id, ResumeWorkExperience.resume_id == resume.id))
    work = result.scalar_one_or_none()
    if not work:
        raise HTTPException(404, "Topilmadi")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(work, k, v)
    await db.commit()
    await db.refresh(work)
    return _work_out(work)


@router.delete("/me/work-experience/{work_id}", status_code=204)
async def delete_work_experience(
    work_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    result = await db.execute(select(ResumeWorkExperience).where(ResumeWorkExperience.id == work_id, ResumeWorkExperience.resume_id == resume.id))
    work = result.scalar_one_or_none()
    if not work:
        raise HTTPException(404, "Topilmadi")
    await db.delete(work)
    await db.commit()


# ── Leadership ────────────────────────────────────────────────────────────────

@router.post("/me/leadership", status_code=201)
async def add_leadership(
    data: LeadershipCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db, create_if_missing=True)
    lead = ResumeLeadership(resume_id=resume.id, **data.model_dump())
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return _lead_out(lead)


@router.patch("/me/leadership/{lead_id}")
async def update_leadership(
    lead_id: uuid.UUID,
    data: LeadershipCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    result = await db.execute(select(ResumeLeadership).where(ResumeLeadership.id == lead_id, ResumeLeadership.resume_id == resume.id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Topilmadi")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(lead, k, v)
    await db.commit()
    await db.refresh(lead)
    return _lead_out(lead)


@router.delete("/me/leadership/{lead_id}", status_code=204)
async def delete_leadership(
    lead_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _load_resume(current_user.id, db)
    if not resume:
        raise HTTPException(404, "Rezyume topilmadi")
    result = await db.execute(select(ResumeLeadership).where(ResumeLeadership.id == lead_id, ResumeLeadership.resume_id == resume.id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Topilmadi")
    await db.delete(lead)
    await db.commit()
