from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import uuid

from app.database import get_db
from app.models.certificate import Certificate
from app.schemas.certificate import CertificateCreate, CertificateOut
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/certificates", tags=["certificates"])


@router.get("", response_model=List[CertificateOut])
async def list_certificates(
    student_id: Optional[uuid.UUID] = Query(None),
    course_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("certificates", "view")),
):
    q = select(Certificate).options(selectinload(Certificate.student), selectinload(Certificate.course))
    if student_id:
        q = q.where(Certificate.student_id == student_id)
    if course_id:
        q = q.where(Certificate.course_id == course_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=CertificateOut, status_code=201)
async def create_certificate(data: CertificateCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("certificates", "create"))):
    serial = data.serial_number or f"EDU-{uuid.uuid4().hex[:8].upper()}"
    cert = Certificate(
        student_id=data.student_id,
        course_id=data.course_id,
        template=data.template,
        issued_date=data.issued_date,
        serial_number=serial,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)
    result = await db.execute(
        select(Certificate)
        .options(selectinload(Certificate.student), selectinload(Certificate.course))
        .where(Certificate.id == cert.id)
    )
    return result.scalar_one()


@router.get("/{cert_id}", response_model=CertificateOut)
async def get_certificate(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(Certificate)
        .options(selectinload(Certificate.student), selectinload(Certificate.course))
        .where(Certificate.id == cert_id)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(404, "Certificate not found")
    return cert


@router.delete("/{cert_id}", status_code=204)
async def delete_certificate(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("certificates", "delete"))):
    result = await db.execute(select(Certificate).where(Certificate.id == cert_id))
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(404, "Not found")
    await db.delete(cert)
    await db.commit()
