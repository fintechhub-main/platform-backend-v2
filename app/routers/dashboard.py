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
from app.dependencies import get_current_user
from app.routers.payments import _billing_periods

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Uzbek month abbreviations
_MONTH_UZ_SHORT = ["Yan", "Fev", "Mar", "Apr", "May", "Iyn", "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek"]
_WEEK_UZ_SHORT  = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]  # Monday=0 .. Sunday=6


@router.get("/stats")
async def get_stats(
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    import uuid as _uuid
    _branch_uuid = _uuid.UUID(branch_id) if branch_id else None
    today = date.today()
    month_start = today.replace(day=1)

    # ── 1. Students ──────────────────────────────────────────────────────────
    total_students = (await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.student)
    )).scalar_one()

    active_students = (await db.execute(
        select(func.count(User.id)).where(
            User.role == UserRole.student,
            User.student_status == "active",
        )
    )).scalar_one()

    new_this_month = (await db.execute(
        select(func.count(User.id)).where(
            User.role == UserRole.student,
            User.created_at >= month_start,
        )
    )).scalar_one()

    # ── 2. Groups ────────────────────────────────────────────────────────────
    total_groups = (await db.execute(select(func.count(Group.id)))).scalar_one()
    active_groups = (await db.execute(
        select(func.count(Group.id)).where(Group.status == GroupStatus.active)
    )).scalar_one()

    # ── 3. Revenue this month ────────────────────────────────────────────────
    monthly_revenue = (await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.date >= month_start)
    )).scalar_one()

    # ── 4. Revenue — last 6 months ───────────────────────────────────────────
    # Build month boundaries for the last 6 calendar months (oldest first)
    last_6_months: list[dict] = []
    for i in range(5, -1, -1):
        # Roll back i months from this month
        offset = today.month - 1 - i
        y = today.year + offset // 12
        m = offset % 12 + 1
        m_start = date(y, m, 1)
        m_end   = date(y, m, calendar.monthrange(y, m)[1])
        total = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.date >= m_start, Payment.date <= m_end)
        )).scalar_one()
        last_6_months.append({
            "month_label": f"{_MONTH_UZ_SHORT[m - 1]} {y}",
            "year": y,
            "month": m,
            "total": int(total),
        })

    # ── 5. Leads ─────────────────────────────────────────────────────────────
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar_one()
    new_leads   = (await db.execute(
        select(func.count(Lead.id)).where(Lead.stage == "yangi")
    )).scalar_one()

    # Leads by stage — one query using conditional aggregation
    stage_list = ["yangi", "aloqa", "sinov", "shartnoma", "faol"]
    lead_stage_rows = (await db.execute(
        select(Lead.stage, func.count(Lead.id).label("cnt"))
        .group_by(Lead.stage)
    )).all()
    leads_by_stage_map = {r.stage: r.cnt for r in lead_stage_rows}
    leads_by_stage = {s: leads_by_stage_map.get(s, 0) for s in stage_list}

    # ── 6. Attendance — today ────────────────────────────────────────────────
    today_att     = (await db.execute(
        select(func.count(Attendance.id)).where(Attendance.date == today)
    )).scalar_one()
    today_present = (await db.execute(
        select(func.count(Attendance.id)).where(
            Attendance.date == today,
            Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late]),
        )
    )).scalar_one()

    # ── 7. Attendance — last 7 days ──────────────────────────────────────────
    week_start = today - timedelta(days=6)

    # Single query: count total and present per day
    att_rows = (await db.execute(
        select(
            Attendance.date,
            func.count(Attendance.id).label("total_count"),
            func.sum(
                case(
                    (Attendance.status.in_([AttendanceStatus.present, AttendanceStatus.online, AttendanceStatus.late]), 1),
                    else_=0,
                )
            ).label("present_count"),
        )
        .where(Attendance.date >= week_start, Attendance.date <= today)
        .group_by(Attendance.date)
        .order_by(Attendance.date)
    )).all()

    att_map = {r.date: (int(r.total_count), int(r.present_count or 0)) for r in att_rows}
    attendance_week = []
    for delta in range(6, -1, -1):
        d = today - timedelta(days=delta)
        total_c, present_c = att_map.get(d, (0, 0))
        pct = round(present_c / total_c * 100) if total_c > 0 else 0
        attendance_week.append({
            "date":          d.isoformat(),
            "label":         _WEEK_UZ_SHORT[d.weekday()],
            "present_count": present_c,
            "total_count":   total_c,
            "pct":           pct,
        })

    # ── 8. Staff count ───────────────────────────────────────────────────────
    staff_count = (await db.execute(
        select(func.count(User.id)).where(
            User.role.in_([UserRole.teacher, UserRole.staff])
        )
    )).scalar_one()

    # ── 9. Top 5 groups by student count ────────────────────────────────────
    top_groups_rows = (await db.execute(
        select(
            Group.id,
            Group.name,
            Group.teacher_id,
            func.count(GroupStudent.id).label("student_count"),
        )
        .outerjoin(GroupStudent, GroupStudent.group_id == Group.id)
        .group_by(Group.id, Group.name, Group.teacher_id)
        .order_by(func.count(GroupStudent.id).desc())
        .limit(5)
    )).all()

    # Fetch teacher names for those groups in one batch
    teacher_ids = {r.teacher_id for r in top_groups_rows if r.teacher_id}
    teacher_name_map: dict[str, str] = {}
    if teacher_ids:
        t_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(teacher_ids))
        )).all()
        teacher_name_map = {str(r.id): r.full_name for r in t_rows}

    top_groups = [
        {
            "group_id":      str(r.id),
            "group_name":    r.name,
            "student_count": int(r.student_count),
            "teacher_name":  teacher_name_map.get(str(r.teacher_id)) if r.teacher_id else None,
        }
        for r in top_groups_rows
    ]

    # ── 10. Recent payments (last 5) ────────────────────────────────────────
    recent_pay_rows = (await db.execute(
        select(
            Payment.id,
            Payment.amount,
            Payment.method,
            Payment.date,
            User.full_name.label("student_name"),
            Group.name.label("group_name"),
        )
        .outerjoin(User,  User.id  == Payment.student_id)
        .outerjoin(Group, Group.id == Payment.group_id)
        .order_by(Payment.date.desc(), Payment.created_at.desc())
        .limit(5)
    )).all()

    recent_payments = [
        {
            "payment_id":   str(r.id),
            "student_name": r.student_name,
            "group_name":   r.group_name,
            "amount":       int(r.amount),
            "method":       r.method.value if r.method else None,
            "date":         r.date.isoformat() if r.date else None,
        }
        for r in recent_pay_rows
    ]

    # ── 11. Overdue payments — top 5 by debt ────────────────────────────────
    # Fetch all active GroupStudent + Group + User rows (active groups only to keep data relevant)
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

    if gs_rows:
        all_student_ids = list({gs.student_id for gs, _, _ in gs_rows})
        all_group_ids   = list({grp.id         for _, grp, _ in gs_rows})

        # Paid per (student_id, group_id) — one query
        paid_q = (
            select(
                Payment.student_id,
                Payment.group_id,
                func.coalesce(func.sum(Payment.amount), 0).label("total_paid"),
            )
            .where(
                Payment.student_id.in_(all_student_ids),
                Payment.group_id.in_(all_group_ids),
            )
            .group_by(Payment.student_id, Payment.group_id)
        )
        paid_map: dict[tuple, int] = {}
        for r in (await db.execute(paid_q)).all():
            paid_map[(str(r.student_id), str(r.group_id))] = int(r.total_paid)

        # Refunded per (student_id, group_id) — one query
        refund_q = (
            select(
                Payment.student_id,
                Payment.group_id,
                func.coalesce(func.sum(PaymentRefund.amount), 0).label("total_refunded"),
            )
            .join(PaymentRefund, PaymentRefund.payment_id == Payment.id)
            .where(
                Payment.student_id.in_(all_student_ids),
                Payment.group_id.in_(all_group_ids),
            )
            .group_by(Payment.student_id, Payment.group_id)
        )
        refund_map: dict[tuple, int] = {}
        for r in (await db.execute(refund_q)).all():
            refund_map[(str(r.student_id), str(r.group_id))] = int(r.total_refunded)

        # Compute debt per (student, group)
        debts: list[dict] = []
        for gs, grp, student in gs_rows:
            sid_str = str(gs.student_id)
            gid_str = str(grp.id)

            payment_start = grp.payment_start_date
            if not payment_start or today < payment_start:
                continue

            pd = max(1, min(28, grp.payment_day or 1))
            periods = _billing_periods(payment_start, pd, today)
            if periods <= 0:
                continue

            price       = grp.price or 0
            first_price = grp.first_month_price if grp.first_month_price is not None else price

            # Simplified total_owed (no discounts for dashboard approximation)
            if periods == 1:
                total_owed = first_price
            else:
                total_owed = first_price + price * (periods - 1)

            net_paid = (
                paid_map.get((sid_str, gid_str), 0)
                - refund_map.get((sid_str, gid_str), 0)
            )
            debt = max(0, total_owed - net_paid)
            if debt <= 0:
                continue

            # days_overdue: how many days since payment_start (proxy for overdue duration)
            days_overdue = (today - payment_start).days

            debts.append({
                "student_id":    sid_str,
                "student_name":  student.full_name,
                "student_phone": student.phone,
                "group_name":    grp.name,
                "debt":          debt,
                "days_overdue":  days_overdue,
            })

        # Top 5 by debt descending
        debts.sort(key=lambda x: x["debt"], reverse=True)
        overdue_payments = debts[:5]

        # Payment status counts (all student-group pairs with billing)
        paid_count    = 0
        partial_count = 0
        debt_count    = 0
        for gs, grp, _ in gs_rows:
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
            if net_paid >= total_owed:
                paid_count += 1
            elif net_paid > 0:
                partial_count += 1
            else:
                debt_count += 1
        payment_stats = {
            "paid":    paid_count,
            "partial": partial_count,
            "debt":    debt_count,
            "total":   paid_count + partial_count + debt_count,
        }
    else:
        payment_stats = {"paid": 0, "partial": 0, "debt": 0, "total": 0}

    # ── 12. Yesterday absentees ─────────────────────────────────────────────
    yesterday = today - timedelta(days=1)
    absent_rows = (await db.execute(
        select(User.id, User.full_name, User.phone, Attendance.group_id)
        .join(Attendance, Attendance.student_id == User.id)
        .where(
            Attendance.date   == yesterday,
            Attendance.status == AttendanceStatus.absent,
        )
        .order_by(User.full_name)
        .limit(20)
    )).all()

    # Get group names in one batch
    abs_group_ids = {r.group_id for r in absent_rows if r.group_id}
    abs_group_map: dict[str, str] = {}
    if abs_group_ids:
        ag_rows = (await db.execute(
            select(Group.id, Group.name).where(Group.id.in_(abs_group_ids))
        )).all()
        abs_group_map = {str(r.id): r.name for r in ag_rows}

    yesterday_absent = [
        {
            "id":    str(r.id),
            "name":  r.full_name,
            "phone": r.phone,
            "group": abs_group_map.get(str(r.group_id)) if r.group_id else "—",
        }
        for r in absent_rows
    ]

    # ── 13. Branch comparison ───────────────────────────────────────────────
    all_branches = (await db.execute(
        select(Branch).where(Branch.is_active == True).order_by(Branch.name)
    )).scalars().all()

    BRANCH_COLORS = ["#4f46e5", "#7c3aed", "#0891b2", "#059669", "#d97706", "#ef4444"]
    branches_comparison = []
    for idx, br in enumerate(all_branches):
        # Active student count (students in active groups of this branch)
        br_students = (await db.execute(
            select(func.count(func.distinct(GroupStudent.student_id)))
            .join(Group, Group.id == GroupStudent.group_id)
            .where(Group.branch_id == br.id, Group.status == GroupStatus.active)
        )).scalar() or 0

        # Revenue this month
        br_revenue = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Group, Group.id == Payment.group_id)
            .where(
                Group.branch_id == br.id,
                func.date_trunc("month", Payment.date) == func.date_trunc("month", func.current_date()),
            )
        )).scalar() or 0

        # Attendance % this month
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
            "id":         str(br.id),
            "name":       br.name,
            "color":      br.color or BRANCH_COLORS[idx % len(BRANCH_COLORS)],
            "students":   int(br_students),
            "revenue":    round(int(br_revenue) / 1_000_000, 1),
            "attendance": att_pct,
        })

    # ── 14. Today's classes (groups with attendance taken today) ────────────
    today_class_rows = (await db.execute(
        select(
            Group.id,
            Group.name,
            Group.schedule,
            Group.teacher_id,
            func.count(Attendance.id).label("student_count"),
        )
        .join(Attendance, Attendance.group_id == Group.id)
        .where(Attendance.date == today)
        .group_by(Group.id, Group.name, Group.schedule, Group.teacher_id)
        .order_by(Group.name)
        .limit(10)
    )).all()

    tc_teacher_ids = {r.teacher_id for r in today_class_rows if r.teacher_id}
    tc_teacher_map: dict[str, str] = {}
    if tc_teacher_ids:
        tc_rows = (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(tc_teacher_ids))
        )).all()
        tc_teacher_map = {str(r.id): r.full_name for r in tc_rows}

    today_classes = [
        {
            "group_id":     str(r.id),
            "group_name":   r.name,
            "teacher_name": tc_teacher_map.get(str(r.teacher_id)) if r.teacher_id else "—",
            "schedule":     r.schedule or "",
            "student_count": int(r.student_count),
        }
        for r in today_class_rows
    ]

    # ── 14. Churn risk (rule-based: attendance + debt) ──────────────────────
    churn_window = today - timedelta(days=30)

    # Attendance per student in last 30 days
    att_stats = (await db.execute(
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
    att_map = {str(r.student_id): (int(r.total), int(r.present or 0)) for r in att_stats}

    # Students in active groups with low attendance or debt
    churn_candidates = []
    for gs, grp, student in gs_rows:   # gs_rows already fetched above (active groups)
        sid_str = str(gs.student_id)
        gid_str = str(grp.id)

        total_att, present_att = att_map.get(sid_str, (0, 0))
        att_pct = round(present_att / total_att * 100) if total_att > 0 else None

        # Debt
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

        # Skip students with good attendance and no debt
        if att_pct is not None and att_pct >= 80 and not has_debt:
            continue
        if att_pct is None and not has_debt:
            continue

        # Risk score 0–100
        risk = 0
        reasons = []
        if att_pct is not None and att_pct < 80:
            risk += int((80 - att_pct) * 1.2)
            reasons.append(f"Davomat: {att_pct}%")
        if has_debt:
            risk += 35
            reasons.append("To'lov kechikdi")
        if att_pct is not None and att_pct < 60:
            risk += 15
        risk = min(risk, 99)

        if risk >= 40:
            churn_candidates.append({
                "id":         sid_str,
                "name":       student.full_name,
                "group":      grp.name,
                "risk":       risk,
                "reasons":    reasons,
                "att_pct":    att_pct,
            })

    churn_candidates.sort(key=lambda x: x["risk"], reverse=True)
    churn_risk = churn_candidates[:10]

    # ── 14. Dropped students (student_status = 'inactive') ──────────────────
    dropped_rows = (await db.execute(
        select(User.id, User.full_name, User.phone, User.updated_at)
        .where(User.role == UserRole.student, User.student_status == "inactive")
        .order_by(User.updated_at.desc().nullslast())
        .limit(20)
    )).all()

    dropped_student_ids = [r.id for r in dropped_rows]
    # Last group per student
    last_group_map: dict[str, str] = {}
    if dropped_student_ids:
        lg_rows = (await db.execute(
            select(GroupStudent.student_id, Group.name)
            .join(Group, Group.id == GroupStudent.group_id)
            .where(GroupStudent.student_id.in_(dropped_student_ids))
            .order_by(GroupStudent.student_id)
        )).all()
        for r in lg_rows:
            last_group_map[str(r.student_id)] = r.name

    dropped_students = [
        {
            "id":        str(r.id),
            "name":      r.full_name,
            "phone":     r.phone,
            "group":     last_group_map.get(str(r.id), "—"),
            "drop_date": r.updated_at.date().isoformat() if r.updated_at else None,
        }
        for r in dropped_rows
    ]

    # ── 14. Birthdays today ──────────────────────────────────────────────────
    birthday_rows = (await db.execute(
        select(User.id, User.full_name, User.role)
        .where(
            func.extract("month", User.birth_date) == today.month,
            func.extract("day",   User.birth_date) == today.day,
            User.birth_date.is_not(None),
        )
    )).all()
    birthdays_today = [
        {
            "id":   str(r.id),
            "name": r.full_name,
            "role": "Ustoz" if r.role in ("teacher", "staff") else "O'quvchi",
        }
        for r in birthday_rows
    ]

    # ── Assemble response ────────────────────────────────────────────────────
    return {
        "students": {
            "total":          total_students,
            "active":         active_students,
            "new_this_month": new_this_month,
        },
        "groups": {
            "total":  total_groups,
            "active": active_groups,
        },
        "revenue": {
            "monthly":       int(monthly_revenue),
            "last_6_months": last_6_months,
        },
        "leads": {
            "total":    total_leads,
            "new":      new_leads,
            "by_stage": leads_by_stage,
        },
        "attendance": {
            "today_total":   today_att,
            "today_present": today_present,
            "week":          attendance_week,
        },
        "staff_count":       staff_count,
        "top_groups":        top_groups,
        "recent_payments":   recent_payments,
        "overdue_payments":  overdue_payments,
        "payment_stats":     payment_stats,
        "birthdays_today":   birthdays_today,
        "yesterday_absent":  yesterday_absent,
        "dropped_students":  dropped_students,
        "churn_risk":        churn_risk,
        "today_classes":     today_classes,
        "branches":          branches_comparison,
    }
