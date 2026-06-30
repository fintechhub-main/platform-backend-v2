import uuid
import calendar
from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.payment import Payment, PaymentRefund
from app.models.payment_log import PaymentLog
from app.models.group import Group, GroupStudent
from app.models.user import User
from app.models.discount import Discount, DiscountStatus, DiscountType
from app.schemas.payment import PaymentCreate, PaymentUpdate, PaymentOut, PaymentRefundCreate, PaymentRefundOut
from app.dependencies import get_current_user, require_admin_or_teacher

router = APIRouter(prefix="/payments", tags=["payments"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _billing_periods(payment_start: date, payment_day: int, as_of: date) -> int:
    """How many billing periods have elapsed up to `as_of` date."""
    pd = max(1, min(28, payment_day))

    if payment_start.day <= pd:
        fb_year, fb_month = payment_start.year, payment_start.month
    else:
        if payment_start.month == 12:
            fb_year, fb_month = payment_start.year + 1, 1
        else:
            fb_year, fb_month = payment_start.year, payment_start.month + 1

    max_day = calendar.monthrange(fb_year, fb_month)[1]
    first_bill = date(fb_year, fb_month, min(pd, max_day))

    if as_of < first_bill:
        return 0

    months_since = (as_of.year - first_bill.year) * 12 + (as_of.month - first_bill.month)
    return months_since + (1 if as_of.day >= pd else 0)


def _apply_discounts(amount: int, discounts: list) -> int:
    """Apply a list of active Discount objects to an amount."""
    result = amount
    for d in discounts:
        if d.discount_type == DiscountType.percent:
            result = int(result * (1 - d.value / 100))
        elif d.discount_type == DiscountType.fixed:
            result = max(0, result - d.value)
    return max(0, result)


def _total_owed_with_discounts(group: Group, periods: int, discounts: list) -> tuple[int, int, int]:
    """
    Returns (total_owed, month1_charge, monthly_charge).
    month1_charge = first_month_price after discounts.
    monthly_charge = price after discounts (for months 2+).
    """
    price = group.price or 0
    first_price = group.first_month_price if group.first_month_price is not None else price

    month1_charge = _apply_discounts(first_price, discounts)
    monthly_charge = _apply_discounts(price, discounts)

    if periods <= 0:
        return 0, month1_charge, monthly_charge
    if periods == 1:
        return month1_charge, month1_charge, monthly_charge
    return month1_charge + monthly_charge * (periods - 1), month1_charge, monthly_charge


def _is_first_month(group: Group, billing_month: date) -> bool:
    pd = max(1, min(28, group.payment_day or 1))
    payment_start = group.payment_start_date
    if not payment_start:
        return False
    periods_at_month_end = _billing_periods(payment_start, pd, billing_month)
    return periods_at_month_end == 1


# ── Standard CRUD ─────────────────────────────────────────────────────────────

def _payment_base(payment: Payment) -> PaymentOut:
    """Convert Payment ORM columns to PaymentOut without touching relationships."""
    return PaymentOut.model_validate({
        c.name: getattr(payment, c.name)
        for c in Payment.__table__.columns
    } | {"refunds": []})


async def _enrich_payment(payment: Payment, db: AsyncSession) -> PaymentOut:
    """Build a PaymentOut with all joined name fields and refund log."""
    out = _payment_base(payment)

    # Fetch all relevant user names in one batch
    uid_set = {
        uid for uid in [
            payment.student_id,
            payment.received_by_id,
            payment.created_by_id,
            payment.updated_by_id,
        ] if uid
    }

    user_map: dict[str, tuple] = {}  # id -> (full_name, phone)
    if uid_set:
        u_rows = (await db.execute(
            select(User.id, User.full_name, User.phone).where(User.id.in_(uid_set))
        )).all()
        for r in u_rows:
            user_map[str(r.id)] = (r.full_name, r.phone)

    if payment.student_id:
        entry = user_map.get(str(payment.student_id))
        if entry:
            out.student_name  = entry[0]
            out.student_phone = entry[1]

    if payment.group_id:
        g_row = (await db.execute(
            select(Group.name, Group.teacher_id).where(Group.id == payment.group_id)
        )).first()
        if g_row:
            out.group_name = g_row.name
            if g_row.teacher_id:
                t_row = (await db.execute(
                    select(User.full_name).where(User.id == g_row.teacher_id)
                )).scalar_one_or_none()
                out.teacher_name = t_row

    out.received_by_name = user_map.get(str(payment.received_by_id), (None,))[0] if payment.received_by_id else None
    out.created_by_name  = user_map.get(str(payment.created_by_id),  (None,))[0] if payment.created_by_id  else None
    out.updated_by_name  = user_map.get(str(payment.updated_by_id),  (None,))[0] if payment.updated_by_id  else None

    # Refund logs
    ref_rows = (await db.execute(
        select(PaymentRefund).where(PaymentRefund.payment_id == payment.id)
        .order_by(PaymentRefund.created_at.asc())
    )).scalars().all()
    refund_outs = []
    if ref_rows:
        ref_user_ids = {r.refunded_by_id for r in ref_rows}
        ru_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(ref_user_ids))
        )).all()
        ru_map = {str(r.id): r.full_name for r in ru_rows}
        for r in ref_rows:
            ro = PaymentRefundOut.model_validate({
                c.name: getattr(r, c.name)
                for c in PaymentRefund.__table__.columns
            })
            ro.refunded_by_name = ru_map.get(str(r.refunded_by_id))
            refund_outs.append(ro)
    out.refunds = refund_outs

    # Edit logs
    log_rows = (await db.execute(
        select(PaymentLog).where(PaymentLog.payment_id == payment.id)
        .order_by(PaymentLog.changed_at.asc())
    )).scalars().all()
    out.logs = [
        {
            "field_name":    r.field_name,
            "old_value":     r.old_value,
            "new_value":     r.new_value,
            "changed_at":    r.changed_at.isoformat() if r.changed_at else None,
            "changed_by_id": str(r.changed_by_id) if r.changed_by_id else None,
        }
        for r in log_rows
    ]
    # Add changed_by names
    log_user_ids = {r.changed_by_id for r in log_rows if r.changed_by_id}
    if log_user_ids:
        lu_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(log_user_ids))
        )).all()
        lu_map = {str(r.id): r.full_name for r in lu_rows}
        for entry in out.logs:
            entry["changed_by_name"] = lu_map.get(entry["changed_by_id"])

    return out


@router.get("", response_model=List[PaymentOut])
async def list_payments(
    student_id: Optional[uuid.UUID] = Query(None),
    group_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(Payment, User.full_name, User.phone, Group.name, Group.teacher_id)
        .outerjoin(User,  User.id  == Payment.student_id)
        .outerjoin(Group, Group.id == Payment.group_id)
    )
    if student_id:
        q = q.where(Payment.student_id == student_id)
    if group_id:
        q = q.where(Payment.group_id == group_id)
    if date_from:
        q = q.where(Payment.date >= date_from)
    if date_to:
        q = q.where(Payment.date <= date_to)
    if branch_id:
        q = q.where(Group.branch_id == uuid.UUID(branch_id))
    rows = (await db.execute(q.offset(skip).limit(limit).order_by(Payment.date.desc()))).all()

    payment_ids = [row[0].id for row in rows]

    # Total refunded per payment in one query
    refund_map: dict[str, int] = {}
    if payment_ids:
        ref_sums = (await db.execute(
            select(PaymentRefund.payment_id, func.sum(PaymentRefund.amount).label("total"))
            .where(PaymentRefund.payment_id.in_(payment_ids))
            .group_by(PaymentRefund.payment_id)
        )).all()
        refund_map = {str(r.payment_id): int(r.total or 0) for r in ref_sums}

    teacher_ids = {row[4] for row in rows if row[4]}
    teacher_map: dict[str, str] = {}
    if teacher_ids:
        t_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(teacher_ids))
        )).all()
        teacher_map = {str(r.id): r.full_name for r in t_rows}

    creator_ids = {row[0].created_by_id for row in rows if row[0].created_by_id} | \
                  {row[0].updated_by_id for row in rows if row[0].updated_by_id}
    creator_map: dict[str, str] = {}
    if creator_ids:
        c_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(creator_ids))
        )).all()
        creator_map = {str(r.id): r.full_name for r in c_rows}

    result = []
    for payment, full_name, phone, group_name, teacher_id in rows:
        out = _payment_base(payment)
        out.student_name    = full_name
        out.student_phone   = phone
        out.group_name      = group_name
        out.teacher_name    = teacher_map.get(str(teacher_id)) if teacher_id else None
        out.created_by_name = creator_map.get(str(payment.created_by_id)) if payment.created_by_id else None
        out.updated_by_name = creator_map.get(str(payment.updated_by_id)) if payment.updated_by_id else None
        out.total_refunded  = refund_map.get(str(payment.id), 0)
        out.refunds         = []
        result.append(out)
    return result


@router.post("", response_model=PaymentOut, status_code=201)
async def create_payment(
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin_or_teacher),
):
    import datetime as dt
    today = date.today()

    # Snapshot active discounts for this student at payment time
    disc_rows = (await db.execute(
        select(Discount).where(
            Discount.student_id == data.student_id,
            Discount.status == DiscountStatus.active.value,
            or_(Discount.start_date.is_(None), Discount.start_date <= today),
            or_(Discount.end_date.is_(None),   Discount.end_date   >= today),
            or_(Discount.group_id.is_(None),   Discount.group_id   == data.group_id),
        )
    )).scalars().all()

    snapshot = [
        {
            "type":  d.discount_type.value,
            "value": d.value,
            "label": f"{d.value}%" if d.discount_type.value == "percent" else f"{d.value:,} so'm",
        }
        for d in disc_rows
    ] if disc_rows else None

    payment = Payment(
        **data.model_dump(),
        created_by_id=current_user.id,
        created_at=dt.datetime.utcnow(),
        discount_snapshot=snapshot,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return await _enrich_payment(payment, db)


@router.patch("/{payment_id}", response_model=PaymentOut)
async def update_payment(
    payment_id: uuid.UUID,
    data: PaymentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin_or_teacher),
):
    import datetime as dt
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Payment not found")

    FIELD_LABELS = {
        "amount": "Summa", "payment_type": "Tur",
        "method": "Usul", "date": "Sana", "description": "Izoh",
    }
    now = dt.datetime.utcnow()
    for k, v in data.model_dump(exclude_none=True).items():
        old_val = getattr(payment, k, None)
        new_val = v
        if str(old_val) != str(new_val):
            db.add(PaymentLog(
                payment_id    = payment.id,
                changed_by_id = current_user.id,
                field_name    = FIELD_LABELS.get(k, k),
                old_value     = str(old_val) if old_val is not None else None,
                new_value     = str(new_val),
                changed_at    = now,
            ))
        setattr(payment, k, new_val)

    payment.updated_by_id = current_user.id
    payment.updated_at    = now
    await db.commit()
    await db.refresh(payment)
    return await _enrich_payment(payment, db)


@router.post("/{payment_id}/refund", response_model=PaymentRefundOut, status_code=201)
async def refund_payment(
    payment_id: uuid.UUID,
    data: PaymentRefundCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin_or_teacher),
):
    row = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Payment not found")
    refund = PaymentRefund(
        payment_id      = payment_id,
        refunded_by_id  = current_user.id,
        amount          = data.amount,
        reason          = data.reason,
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)
    out = PaymentRefundOut.model_validate({
        c.name: getattr(refund, c.name)
        for c in PaymentRefund.__table__.columns
    })
    out.refunded_by_name = current_user.full_name
    return out


@router.delete("/{payment_id}", status_code=204)
async def delete_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Payment not found")
    await db.delete(payment)
    await db.commit()


# ── Debt summary ──────────────────────────────────────────────────────────────

@router.get("/debt-summary")
async def debt_summary(
    student_id: Optional[uuid.UUID] = Query(None),
    student_ids: Optional[str] = Query(None),  # comma-separated UUIDs
    group_id: Optional[uuid.UUID] = Query(None),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Return debt per (student, group) pair, considering payment_start_date and first_month_price."""
    today = date.today()

    # 1. Fetch all (GroupStudent, Group, User) rows
    gs_q = (
        select(GroupStudent, Group, User)
        .join(Group, Group.id == GroupStudent.group_id)
        .join(User, User.id == GroupStudent.student_id)
    )
    if student_id:
        gs_q = gs_q.where(GroupStudent.student_id == student_id)
    elif student_ids:
        id_list = [uuid.UUID(s.strip()) for s in student_ids.split(',') if s.strip()]
        if id_list:
            gs_q = gs_q.where(GroupStudent.student_id.in_(id_list))
    if group_id:
        gs_q = gs_q.where(GroupStudent.group_id == group_id)
    if branch_id:
        gs_q = gs_q.where(Group.branch_id == uuid.UUID(branch_id))

    rows = (await db.execute(gs_q)).all()
    if not rows:
        return []

    student_ids = list({gs.student_id for gs, _, _ in rows})
    group_ids   = list({group.id for _, group, _ in rows})

    # 2. Fetch all payments and refunds, group by (student_id, group_id)
    paid_q = (
        select(Payment.student_id, Payment.group_id, func.sum(Payment.amount).label("total"))
        .where(Payment.student_id.in_(student_ids), Payment.group_id.in_(group_ids))
        .group_by(Payment.student_id, Payment.group_id)
    )
    paid_map: dict[tuple, int] = {}
    for row in (await db.execute(paid_q)).all():
        paid_map[(str(row.student_id), str(row.group_id))] = int(row.total or 0)

    # Subtract refunded amounts from paid_map
    refund_q = (
        select(Payment.student_id, Payment.group_id, func.sum(PaymentRefund.amount).label("refunded"))
        .join(PaymentRefund, PaymentRefund.payment_id == Payment.id)
        .where(Payment.student_id.in_(student_ids), Payment.group_id.in_(group_ids))
        .group_by(Payment.student_id, Payment.group_id)
    )
    for row in (await db.execute(refund_q)).all():
        key = (str(row.student_id), str(row.group_id))
        paid_map[key] = max(0, paid_map.get(key, 0) - int(row.refunded or 0))

    # 3. Fetch all active discounts in one query
    disc_q = (
        select(Discount)
        .where(
            Discount.student_id.in_(student_ids),
            Discount.status == DiscountStatus.active.value,
            or_(Discount.start_date.is_(None), Discount.start_date <= today),
            or_(Discount.end_date.is_(None), Discount.end_date >= today),
        )
    )
    disc_rows = (await db.execute(disc_q)).scalars().all()

    # Index discounts by student_id
    disc_map: dict[str, list] = {}
    for d in disc_rows:
        sid_str = str(d.student_id)
        disc_map.setdefault(sid_str, []).append(d)

    # 4. Calculate per-(student, group)
    results = []
    for gs, group, student in rows:
        sid, gid = gs.student_id, group.id
        sid_str, gid_str = str(sid), str(gid)

        total_paid = paid_map.get((sid_str, gid_str), 0)

        # Filter discounts: student-level global OR this specific group
        all_student_discounts = disc_map.get(sid_str, [])
        active_discounts = [
            d for d in all_student_discounts
            if d.group_id is None or str(d.group_id) == gid_str
        ]

        payment_start = group.payment_start_date
        pd = max(1, min(28, group.payment_day or 1))

        if not payment_start or today < payment_start:
            periods = 0
            next_due = payment_start
            price = group.price or 0
            first_price = group.first_month_price if group.first_month_price is not None else price
            month1_charge = _apply_discounts(first_price, active_discounts)
            monthly_charge = _apply_discounts(price, active_discounts)
            total_owed = 0
        else:
            periods = _billing_periods(payment_start, pd, today)
            total_owed, month1_charge, monthly_charge = _total_owed_with_discounts(group, periods, active_discounts)
            if payment_start.day <= pd:
                fb_y, fb_m = payment_start.year, payment_start.month
            else:
                fb_y, fb_m = (payment_start.year + 1, 1) if payment_start.month == 12 else (payment_start.year, payment_start.month + 1)
            offset_m = fb_m + periods
            nd_y = fb_y + (offset_m - 1) // 12
            nd_m = (offset_m - 1) % 12 + 1
            next_due = date(nd_y, nd_m, min(pd, calendar.monthrange(nd_y, nd_m)[1]))

        debt = max(0, total_owed - total_paid)

        results.append({
            "student_id": sid_str,
            "student_name": student.full_name,
            "student_phone": student.phone,
            "group_id": gid_str,
            "group_name": group.name,
            "price": group.price or 0,
            "first_month_price": group.first_month_price,
            "month1_charge": month1_charge,
            "monthly_charge": monthly_charge,
            "total_owed": total_owed,
            "total_paid": total_paid,
            "debt": debt,
            "periods_billed": periods,
            "next_due_date": next_due.isoformat() if next_due else None,
            "discounts": [
                {"type": d.discount_type.value, "value": d.value}
                for d in active_discounts
            ],
        })

    return results


# ── Student month summary ─────────────────────────────────────────────────────

_MONTH_UZ = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"]

@router.get("/student-month-summary")
async def student_month_summary(
    student_id: uuid.UUID = Query(...),
    group_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    today = date.today()

    group = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Group not found")

    payment_start = group.payment_start_date
    if not payment_start or today < payment_start:
        return []

    pd = max(1, min(28, group.payment_day or 1))
    price       = group.price or 0
    first_price = group.first_month_price if group.first_month_price is not None else price

    periods = _billing_periods(payment_start, pd, today)
    if periods == 0:
        return []

    # Fetch active discounts for this student/group
    disc_rows = (await db.execute(
        select(Discount).where(
            Discount.student_id == student_id,
            Discount.status == DiscountStatus.active.value,
            or_(Discount.start_date.is_(None), Discount.start_date <= today),
            or_(Discount.end_date.is_(None),   Discount.end_date   >= today),
            or_(Discount.group_id.is_(None),   Discount.group_id   == group_id),
        )
    )).scalars().all()

    discounts_info = [
        {
            "type":  d.discount_type.value,
            "value": d.value,
        }
        for d in disc_rows
    ]

    first_price_eff = _apply_discounts(first_price, disc_rows)
    price_eff       = _apply_discounts(price,       disc_rows)

    # First billing month
    if payment_start.day <= pd:
        fb_y, fb_m = payment_start.year, payment_start.month
    else:
        if payment_start.month == 12:
            fb_y, fb_m = payment_start.year + 1, 1
        else:
            fb_y, fb_m = payment_start.year, payment_start.month + 1

    # Fetch total net paid (payments minus refunds) for this (student, group)
    pay_rows = (await db.execute(
        select(Payment.id, Payment.amount)
        .where(Payment.student_id == student_id, Payment.group_id == group_id)
    )).all()

    total_gross = sum(r.amount for r in pay_rows)

    refund_total = 0
    if pay_rows:
        ref_row = (await db.execute(
            select(func.sum(PaymentRefund.amount))
            .where(PaymentRefund.payment_id.in_([r.id for r in pay_rows]))
        )).scalar()
        refund_total = int(ref_row or 0)

    remaining_paid = max(0, total_gross - refund_total)

    # Allocate cumulatively: period 1 gets first_price, periods 2+ get price
    months = []
    for i in range(periods):
        offset = fb_m + i - 1
        y = fb_y + offset // 12
        m = offset % 12 + 1
        due = first_price_eff if i == 0 else price_eff
        allocated = min(remaining_paid, due)
        remaining_paid -= allocated

        months.append({
            "month_number": i + 1,
            "year": y,
            "month": m,
            "label": f"{_MONTH_UZ[m - 1]} {y}",
            "amount_due": due,
            "amount_paid": allocated,
            "balance": allocated - due,
            "is_paid": allocated >= due,
        })

    return {"months": months, "discounts": discounts_info, "price": price, "first_price": first_price}


# ── Teacher salary ────────────────────────────────────────────────────────────

@router.get("/teacher-salary")
async def teacher_salary(
    year: int = Query(...),
    month: int = Query(...),
    teacher_id: Optional[uuid.UUID] = Query(None),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Calculate teacher salary for a given month.
    Uses first_month_price for students in their 1st billing period,
    price for subsequent months.
    Salary = group_revenue × salary_percent/100  OR  fixed teacher_salary_value.
    """
    groups_q = (
        select(Group)
        .options(joinedload(Group.teacher))
    )
    if teacher_id:
        groups_q = groups_q.where(Group.teacher_id == teacher_id)
    if branch_id:
        groups_q = groups_q.where(Group.branch_id == uuid.UUID(branch_id))

    groups = (await db.execute(groups_q)).unique().scalars().all()

    # Last day of the target month
    billing_date = date(year, month, calendar.monthrange(year, month)[1])
    today = date.today()

    results = []
    teachers_seen: dict[uuid.UUID, dict] = {}

    for group in groups:
        if not group.teacher_id:
            continue
        tid = group.teacher_id

        # Students in this group
        stu_rows = (await db.execute(
            select(GroupStudent, User)
            .join(User, User.id == GroupStudent.student_id)
            .where(GroupStudent.group_id == group.id)
        )).all()

        payment_start = group.payment_start_date  # no fallback — only explicit billing start
        pd = max(1, min(28, group.payment_day or 1))
        price = group.price or 0
        first_price = group.first_month_price if group.first_month_price is not None else price

        group_revenue = 0
        student_details = []
        from datetime import timedelta
        for gs, stu in stu_rows:
            if not payment_start:
                continue
            target_end = min(billing_date, today)
            periods = _billing_periods(payment_start, pd, target_end)
            if periods <= 0:
                continue
            prev_day = date(year, month, 1) - timedelta(days=1)
            periods_before = _billing_periods(payment_start, pd, prev_day) if date(year, month, 1) > payment_start else 0
            period_this_month = periods - periods_before
            if period_this_month <= 0:
                continue

            # Base price for this period
            base_price = first_price if periods_before == 0 else price

            # Apply student's active discounts
            disc_q = (
                select(Discount)
                .where(
                    Discount.student_id == gs.student_id,
                    Discount.status == DiscountStatus.active,
                    or_(Discount.group_id == group.id, Discount.group_id.is_(None)),
                    or_(Discount.start_date.is_(None), Discount.start_date <= billing_date),
                    or_(Discount.end_date.is_(None), Discount.end_date >= billing_date),
                )
            )
            student_discounts = (await db.execute(disc_q)).scalars().all()
            student_price = _apply_discounts(base_price, student_discounts)

            group_revenue += student_price
            student_details.append({
                "student_name": stu.full_name,
                "base_price": base_price,
                "price": student_price,
                "is_first_month": periods_before == 0,
                "discounts": [{"type": d.discount_type.value, "value": d.value} for d in student_discounts],
            })

        # Teacher earning from this group
        salary_type = group.teacher_salary_type
        salary_value = group.teacher_salary_value or 0
        if salary_type == "percent":
            teacher_earning = int(group_revenue * salary_value / 100)
        elif salary_type == "fixed":
            teacher_earning = salary_value
        else:
            teacher_earning = 0

        if tid not in teachers_seen:
            t = group.teacher
            teachers_seen[tid] = {
                "teacher_id": str(tid),
                "teacher_name": t.full_name if t else "—",
                "teacher_phone": t.phone if t else None,
                "total_salary": 0,
                "groups": [],
            }

        teachers_seen[tid]["total_salary"] += teacher_earning
        teachers_seen[tid]["groups"].append({
            "group_id": str(group.id),
            "group_name": group.name,
            "student_count": len(student_details),
            "group_revenue": group_revenue,
            "salary_type": salary_type,
            "salary_value": salary_value,
            "teacher_earning": teacher_earning,
            "students": student_details,
        })

    return list(teachers_seen.values())


# ── Single payment detail (must be LAST to avoid shadowing static routes) ─────

@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    row = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Payment not found")
    return await _enrich_payment(row, db)
