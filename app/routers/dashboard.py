import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, literal_column

from app.database import get_db
from app.models.user import User, UserRole
from app.models.group import Group, GroupStatus, GroupStudent
from app.models.payment import Payment, PaymentRefund
from app.models.attendance import Attendance, AttendanceStatus
from app.models.student import Lead
from app.models.branch import Branch
from app.dependencies import get_current_user, require_permission
from app.routers.payments import _billing_periods

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_MONTH_UZ_SHORT = ["Yan", "Fev", "Mar", "Apr", "May", "Iyn", "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek"]
_WEEK_UZ_SHORT  = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]


@router.get("/stats")
async def get_stats(
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard", "view")),
):
    import uuid as _uuid
    _branch_uuid = _uuid.UUID(branch_id) if branch_id else None
    today = date.today()
    month_start = today.replace(day=1)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _branch_group_filter(q):
        """Add branch filter to a query that already joins Group."""
        if _branch_uuid:
            q = q.where(Group.branch_id == _branch_uuid)
        return q

    # ── 1. Students ───────────────────────────────────────────────────────────
    if _branch_uuid:
        # students who are members of at least one group in this branch
        branch_student_ids_sq = (
            select(GroupStudent.student_id)
            .join(Group, Group.id == GroupStudent.group_id)
            .where(Group.branch_id == _branch_uuid)
            .distinct()
            .scalar_subquery()
        )
        base_student = select(func.count(User.id)).where(
            User.role == UserRole.student,
            User.id.in_(branch_student_ids_sq),
        )
    else:
        base_student = select(func.count(User.id)).where(User.role == UserRole.student)

    total_students = (await db.execute(base_student)).scalar_one()
    active_students = (await db.execute(
        base_student.where(User.student_status == "active")
        if not _branch_uuid
        else select(func.count(User.id)).where(
            User.role == UserRole.student,
            User.id.in_(branch_student_ids_sq),
            User.student_status == "active",
        )
    )).scalar_one()
    new_this_month = (await db.execute(
        select(func.count(User.id)).where(
            User.role == UserRole.student,
            User.created_at >= month_start,
            *([User.id.in_(branch_student_ids_sq)] if _branch_uuid else []),
        )
    )).scalar_one()

    # ── 2. Groups ─────────────────────────────────────────────────────────────
    _g_where = [Group.branch_id == _branch_uuid] if _branch_uuid else []
    total_groups = (await db.execute(
        select(func.count(Group.id)).where(*_g_where)
    )).scalar_one()
    active_groups = (await db.execute(
        select(func.count(Group.id)).where(Group.status == GroupStatus.active, *_g_where)
    )).scalar_one()

    # ── 3. Revenue this month ─────────────────────────────────────────────────
    _pay_q = select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.date >= month_start)
    if _branch_uuid:
        _pay_q = _pay_q.join(Group, Group.id == Payment.group_id).where(Group.branch_id == _branch_uuid)
    monthly_revenue = (await db.execute(_pay_q)).scalar_one()

    # ── 4. Revenue last 6 months ──────────────────────────────────────────────
    last_6_months: list[dict] = []
    for i in range(5, -1, -1):
        offset = today.month - 1 - i
        y = today.year + offset // 12
        m = offset % 12 + 1
        m_start = date(y, m, 1)
        m_end   = date(y, m, calendar.monthrange(y, m)[1])
        q6 = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.date >= m_start, Payment.date <= m_end
        )
        if _branch_uuid:
            q6 = q6.join(Group, Group.id == Payment.group_id).where(Group.branch_id == _branch_uuid)
        total = (await db.execute(q6)).scalar_one()
        last_6_months.append({
            "month_label": f"{_MONTH_UZ_SHORT[m - 1]} {y}",
            "year": y, "month": m, "total": int(total),
        })

    # ── 5. Leads ──────────────────────────────────────────────────────────────
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar_one()
    new_leads   = (await db.execute(
        select(func.count(Lead.id)).where(Lead.stage == "yangi")
    )).scalar_one()
    stage_list = ["yangi", "aloqa", "sinov", "shartnoma", "faol"]
    lead_stage_rows = (await db.execute(
        select(Lead.stage, func.count(Lead.id).label("cnt")).group_by(Lead.stage)
    )).all()
    leads_by_stage_map = {r.stage: r.cnt for r in lead_stage_rows}
    leads_by_stage = {s: leads_by_stage_map.get(s, 0) for s in stage_list}

    # ── 6. Attendance today ───────────────────────────────────────────────────
    _att_today_base = select(func.count(Attendance.id)).where(Attendance.date == today)
    if _branch_uuid:
        _att_today_base = _att_today_base.join(Group, Group.id == Attendance.group_id).where(Group.branch_id == _branch_uuid)
    today_att     = (await db.execute(_att_today_base)).scalar_one()
    today_present = (await db.execute(
        _att_today_base.where(
            Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late])
        )
        if not _branch_uuid
        else select(func.count(Attendance.id))
            .join(Group, Group.id == Attendance.group_id)
            .where(
                Attendance.date == today,
                Group.branch_id == _branch_uuid,
                Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late]),
            )
    )).scalar_one()

    # ── 7. Attendance last 7 days ─────────────────────────────────────────────
    week_start = today - timedelta(days=6)
    _att_week_q = (
        select(
            Attendance.date,
            func.count(Attendance.id).label("total_count"),
            func.sum(case(
                (Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late]), 1),
                else_=0,
            )).label("present_count"),
        )
        .where(Attendance.date >= week_start, Attendance.date <= today)
        .group_by(Attendance.date)
        .order_by(Attendance.date)
    )
    if _branch_uuid:
        _att_week_q = _att_week_q.join(Group, Group.id == Attendance.group_id).where(Group.branch_id == _branch_uuid)
    att_rows = (await db.execute(_att_week_q)).all()
    att_map_week = {r.date: (int(r.total_count), int(r.present_count or 0)) for r in att_rows}
    attendance_week = []
    for delta in range(6, -1, -1):
        d = today - timedelta(days=delta)
        total_c, present_c = att_map_week.get(d, (0, 0))
        pct = round(present_c / total_c * 100) if total_c > 0 else 0
        attendance_week.append({
            "date": d.isoformat(), "label": _WEEK_UZ_SHORT[d.weekday()],
            "present_count": present_c, "total_count": total_c, "pct": pct,
        })

    # ── 8. Staff count ────────────────────────────────────────────────────────
    if _branch_uuid:
        teacher_ids_in_branch = (
            select(Group.teacher_id)
            .where(Group.branch_id == _branch_uuid, Group.teacher_id.isnot(None))
            .distinct()
            .scalar_subquery()
        )
        staff_count = (await db.execute(
            select(func.count(User.id)).where(
                User.role.in_([UserRole.teacher, UserRole.staff]),
                User.id.in_(teacher_ids_in_branch),
            )
        )).scalar_one()
    else:
        staff_count = (await db.execute(
            select(func.count(User.id)).where(User.role.in_([UserRole.teacher, UserRole.staff]))
        )).scalar_one()

    # ── 9. Top 5 groups ───────────────────────────────────────────────────────
    _top_g_q = (
        select(
            Group.id, Group.name, Group.teacher_id,
            func.count(GroupStudent.id).label("student_count"),
        )
        .outerjoin(GroupStudent, GroupStudent.group_id == Group.id)
        .group_by(Group.id, Group.name, Group.teacher_id)
        .order_by(func.count(GroupStudent.id).desc())
        .limit(5)
    )
    if _branch_uuid:
        _top_g_q = _top_g_q.where(Group.branch_id == _branch_uuid)
    top_groups_rows = (await db.execute(_top_g_q)).all()
    teacher_ids_set = {r.teacher_id for r in top_groups_rows if r.teacher_id}
    teacher_name_map: dict[str, str] = {}
    if teacher_ids_set:
        t_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(teacher_ids_set))
        )).all()
        teacher_name_map = {str(r.id): r.full_name for r in t_rows}
    top_groups = [
        {
            "group_id": str(r.id), "group_name": r.name,
            "student_count": int(r.student_count),
            "teacher_name": teacher_name_map.get(str(r.teacher_id)) if r.teacher_id else None,
        }
        for r in top_groups_rows
    ]

    # ── 10. Recent payments ───────────────────────────────────────────────────
    _recent_pay_q = (
        select(Payment.id, Payment.amount, Payment.method, Payment.date,
               User.full_name.label("student_name"), Group.name.label("group_name"))
        .outerjoin(User,  User.id  == Payment.student_id)
        .outerjoin(Group, Group.id == Payment.group_id)
        .order_by(Payment.date.desc(), Payment.created_at.desc())
        .limit(5)
    )
    if _branch_uuid:
        _recent_pay_q = _recent_pay_q.where(Group.branch_id == _branch_uuid)
    recent_pay_rows = (await db.execute(_recent_pay_q)).all()
    recent_payments = [
        {
            "payment_id": str(r.id), "student_name": r.student_name,
            "group_name": r.group_name, "amount": int(r.amount),
            "method": r.method.value if r.method else None,
            "date": r.date.isoformat() if r.date else None,
        }
        for r in recent_pay_rows
    ]

    # ── 11. Overdue payments + payment stats ─────────────────────────────────
    _gs_where = [Group.status == GroupStatus.active]
    if _branch_uuid:
        _gs_where.append(Group.branch_id == _branch_uuid)
    gs_rows = (await db.execute(
        select(GroupStudent, Group, User)
        .join(Group, Group.id == GroupStudent.group_id)
        .join(User,  User.id  == GroupStudent.student_id)
        .where(*_gs_where)
    )).all()

    overdue_payments: list[dict] = []
    payment_stats = {"paid": 0, "partial": 0, "debt": 0, "total": 0}

    if gs_rows:
        all_student_ids = list({gs.student_id for gs, _, _ in gs_rows})
        all_group_ids   = list({grp.id         for _, grp, _ in gs_rows})
        paid_map: dict[tuple, int] = {}
        for r in (await db.execute(
            select(Payment.student_id, Payment.group_id,
                   func.coalesce(func.sum(Payment.amount), 0).label("total_paid"))
            .where(Payment.student_id.in_(all_student_ids), Payment.group_id.in_(all_group_ids))
            .group_by(Payment.student_id, Payment.group_id)
        )).all():
            paid_map[(str(r.student_id), str(r.group_id))] = int(r.total_paid)

        refund_map: dict[tuple, int] = {}
        for r in (await db.execute(
            select(Payment.student_id, Payment.group_id,
                   func.coalesce(func.sum(PaymentRefund.amount), 0).label("total_refunded"))
            .join(PaymentRefund, PaymentRefund.payment_id == Payment.id)
            .where(Payment.student_id.in_(all_student_ids), Payment.group_id.in_(all_group_ids))
            .group_by(Payment.student_id, Payment.group_id)
        )).all():
            refund_map[(str(r.student_id), str(r.group_id))] = int(r.total_refunded)

        debts: list[dict] = []
        paid_count = partial_count = debt_count = 0
        for gs, grp, student in gs_rows:
            sid_str = str(gs.student_id)
            gid_str = str(grp.id)
            payment_start = grp.payment_start_date
            if not payment_start or today < payment_start:
                continue
            pd      = max(1, min(28, grp.payment_day or 1))
            periods = _billing_periods(payment_start, pd, today)
            if periods <= 0:
                continue
            price       = grp.price or 0
            first_price = grp.first_month_price if grp.first_month_price is not None else price
            total_owed  = first_price + price * (periods - 1) if periods > 1 else first_price
            net_paid    = paid_map.get((sid_str, gid_str), 0) - refund_map.get((sid_str, gid_str), 0)
            debt        = max(0, total_owed - net_paid)

            if net_paid >= total_owed:
                paid_count += 1
            elif net_paid > 0:
                partial_count += 1
            else:
                debt_count += 1

            if debt > 0:
                debts.append({
                    "student_id": sid_str, "student_name": student.full_name,
                    "student_phone": student.phone, "group_name": grp.name,
                    "debt": debt, "days_overdue": (today - payment_start).days,
                })

        debts.sort(key=lambda x: x["debt"], reverse=True)
        overdue_payments = debts[:5]
        payment_stats = {
            "paid": paid_count, "partial": partial_count,
            "debt": debt_count, "total": paid_count + partial_count + debt_count,
        }

    # ── 12. Yesterday absentees ───────────────────────────────────────────────
    # Ro'yxat ko'rsatish uchun 20 taga cheklangan, lekin "jami" son alohida,
    # cheklovsiz so'rov bilan hisoblanadi — aks holda frontend "20 kishi"
    # deb ko'rsatib, haqiqiy sonni (masalan 96) yashirib qo'yardi.
    yesterday = today - timedelta(days=1)
    _abs_count_q = (
        select(func.count(Attendance.id))
        .where(Attendance.date == yesterday, Attendance.status == AttendanceStatus.absent)
    )
    if _branch_uuid:
        _abs_count_q = _abs_count_q.join(Group, Group.id == Attendance.group_id).where(Group.branch_id == _branch_uuid)
    yesterday_absent_total = (await db.execute(_abs_count_q)).scalar_one()

    _abs_q = (
        select(User.id, User.full_name, User.phone, Attendance.group_id)
        .join(Attendance, Attendance.student_id == User.id)
        .where(Attendance.date == yesterday, Attendance.status == AttendanceStatus.absent)
        .order_by(User.full_name).limit(20)
    )
    if _branch_uuid:
        _abs_q = _abs_q.join(Group, Group.id == Attendance.group_id).where(Group.branch_id == _branch_uuid)
    absent_rows = (await db.execute(_abs_q)).all()
    abs_group_ids = {r.group_id for r in absent_rows if r.group_id}
    abs_group_map: dict[str, str] = {}
    if abs_group_ids:
        ag_rows = (await db.execute(
            select(Group.id, Group.name).where(Group.id.in_(abs_group_ids))
        )).all()
        abs_group_map = {str(r.id): r.name for r in ag_rows}
    yesterday_absent = [
        {"id": str(r.id), "name": r.full_name, "phone": r.phone,
         "group": abs_group_map.get(str(r.group_id)) if r.group_id else "—"}
        for r in absent_rows
    ]

    # ── 13. Branch comparison ─────────────────────────────────────────────────
    all_branches = (await db.execute(
        select(Branch).where(Branch.is_active == True).order_by(Branch.name)
    )).scalars().all()
    BRANCH_COLORS = ["#4f46e5", "#7c3aed", "#0891b2", "#059669", "#d97706", "#ef4444"]
    branches_comparison = []
    for idx, br in enumerate(all_branches):
        br_students = (await db.execute(
            select(func.count(func.distinct(GroupStudent.student_id)))
            .join(Group, Group.id == GroupStudent.group_id)
            .where(Group.branch_id == br.id, Group.status == GroupStatus.active)
        )).scalar() or 0
        br_revenue = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Group, Group.id == Payment.group_id)
            .where(
                Group.branch_id == br.id,
                func.date_trunc("month", Payment.date) == func.date_trunc("month", func.current_date()),
            )
        )).scalar() or 0
        br_att = (await db.execute(
            select(
                func.count(Attendance.id).label("total"),
                func.sum(case(
                    (Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late]), 1),
                    else_=0,
                )).label("present"),
            )
            .join(Group, Group.id == Attendance.group_id)
            .where(
                Group.branch_id == br.id,
                func.date_trunc("month", Attendance.date) == func.date_trunc("month", func.current_date()),
            )
        )).one()
        att_pct = round(int(br_att.present or 0) / int(br_att.total) * 100) if br_att.total else 0
        branches_comparison.append({
            "id": str(br.id), "name": br.name,
            "color": br.color or BRANCH_COLORS[idx % len(BRANCH_COLORS)],
            "students": int(br_students),
            "revenue": round(int(br_revenue) / 1_000_000, 1),
            "attendance": att_pct,
        })

    # ── 14. Today's classes ───────────────────────────────────────────────────
    _tc_q = (
        select(Group.id, Group.name, Group.schedule, Group.teacher_id,
               func.count(Attendance.id).label("student_count"))
        .join(Attendance, Attendance.group_id == Group.id)
        .where(Attendance.date == today)
        .group_by(Group.id, Group.name, Group.schedule, Group.teacher_id)
        .order_by(Group.name).limit(10)
    )
    if _branch_uuid:
        _tc_q = _tc_q.where(Group.branch_id == _branch_uuid)
    today_class_rows = (await db.execute(_tc_q)).all()
    tc_teacher_ids = {r.teacher_id for r in today_class_rows if r.teacher_id}
    tc_teacher_map: dict[str, str] = {}
    if tc_teacher_ids:
        tc_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(tc_teacher_ids))
        )).all()
        tc_teacher_map = {str(r.id): r.full_name for r in tc_rows}
    today_classes = [
        {
            "group_id": str(r.id), "group_name": r.name,
            "teacher_name": tc_teacher_map.get(str(r.teacher_id)) if r.teacher_id else "—",
            "schedule": r.schedule or "", "student_count": int(r.student_count),
        }
        for r in today_class_rows
    ]

    # ── 15. Churn risk ────────────────────────────────────────────────────────
    churn_window = today - timedelta(days=30)
    att_stats_rows = (await db.execute(
        select(
            Attendance.student_id,
            func.count(Attendance.id).label("total"),
            func.sum(case(
                (Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late]), 1),
                else_=0,
            )).label("present"),
        )
        .where(Attendance.date >= churn_window, Attendance.date <= today)
        .group_by(Attendance.student_id)
    )).all()
    att_map_churn = {str(r.student_id): (int(r.total), int(r.present or 0)) for r in att_stats_rows}
    churn_candidates = []
    for gs, grp, student in gs_rows:
        sid_str = str(gs.student_id)
        gid_str = str(grp.id)
        total_att, present_att = att_map_churn.get(sid_str, (0, 0))
        att_pct_c = round(present_att / total_att * 100) if total_att > 0 else None
        payment_start = grp.payment_start_date
        has_debt = False
        if payment_start and today >= payment_start:
            pd = max(1, min(28, grp.payment_day or 1))
            periods = _billing_periods(payment_start, pd, today)
            if periods > 0:
                price = grp.price or 0
                first_price = grp.first_month_price if grp.first_month_price is not None else price
                total_owed = first_price + price * (periods - 1) if periods > 1 else first_price
                net_paid = paid_map.get((sid_str, gid_str), 0) - refund_map.get((sid_str, gid_str), 0)
                has_debt = net_paid < total_owed
        if att_pct_c is not None and att_pct_c >= 80 and not has_debt:
            continue
        if att_pct_c is None and not has_debt:
            continue
        risk = 0
        reasons = []
        if att_pct_c is not None and att_pct_c < 80:
            risk += int((80 - att_pct_c) * 1.2)
            reasons.append(f"Davomat: {att_pct_c}%")
        if has_debt:
            risk += 35
            reasons.append("To'lov kechikdi")
        if att_pct_c is not None and att_pct_c < 60:
            risk += 15
        risk = min(risk, 99)
        if risk >= 40:
            churn_candidates.append({
                "id": sid_str, "name": student.full_name,
                "group": grp.name, "risk": risk,
                "reasons": reasons, "att_pct": att_pct_c,
            })
    churn_candidates.sort(key=lambda x: x["risk"], reverse=True)
    churn_risk = churn_candidates[:10]

    # ── 16. Dropped students ──────────────────────────────────────────────────
    _drop_q = (
        select(User.id, User.full_name, User.phone, User.created_at)
        .where(User.role == UserRole.student, User.student_status == "inactive")
        .order_by(User.created_at.desc().nullslast()).limit(20)
    )
    if _branch_uuid:
        _drop_q = _drop_q.where(User.id.in_(branch_student_ids_sq))
    dropped_rows = (await db.execute(_drop_q)).all()
    dropped_student_ids = [r.id for r in dropped_rows]
    last_group_map: dict[str, str] = {}
    if dropped_student_ids:
        for r in (await db.execute(
            select(GroupStudent.student_id, Group.name)
            .join(Group, Group.id == GroupStudent.group_id)
            .where(GroupStudent.student_id.in_(dropped_student_ids))
            .order_by(GroupStudent.student_id)
        )).all():
            last_group_map[str(r.student_id)] = r.name
    dropped_students = [
        {
            "id": str(r.id), "name": r.full_name, "phone": r.phone,
            "group": last_group_map.get(str(r.id), "—"),
            "drop_date": r.created_at.date().isoformat() if r.created_at else None,
        }
        for r in dropped_rows
    ]

    # ── 17. Birthdays today ───────────────────────────────────────────────────
    birthday_rows = (await db.execute(
        select(User.id, User.full_name, User.role)
        .where(
            func.extract("month", User.birth_date) == today.month,
            func.extract("day",   User.birth_date) == today.day,
            User.birth_date.is_not(None),
        )
    )).all()
    birthdays_today = [
        {"id": str(r.id), "name": r.full_name,
         "role": "Ustoz" if r.role in ("teacher", "staff") else "O'quvchi"}
        for r in birthday_rows
    ]

    return {
        "students": {
            "total": total_students, "active": active_students, "new_this_month": new_this_month,
        },
        "groups": {"total": total_groups, "active": active_groups},
        "revenue": {"monthly": int(monthly_revenue), "last_6_months": last_6_months},
        "leads":   {"total": total_leads, "new": new_leads, "by_stage": leads_by_stage},
        "attendance": {
            "today_total": today_att, "today_present": today_present, "week": attendance_week,
        },
        "staff_count":      staff_count,
        "top_groups":       top_groups,
        "recent_payments":  recent_payments,
        "overdue_payments": overdue_payments,
        "payment_stats":    payment_stats,
        "birthdays_today":  birthdays_today,
        "yesterday_absent": yesterday_absent,
        "yesterday_absent_total": yesterday_absent_total,
        "dropped_students": dropped_students,
        "churn_risk":       churn_risk,
        "today_classes":    today_classes,
        "branches":         branches_comparison,
    }
