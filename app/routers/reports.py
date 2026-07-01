import calendar
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User, UserRole
from app.models.group import Group, GroupStatus, GroupStudent
from app.models.course import Course
from app.models.payment import Payment, PaymentRefund
from app.models.attendance import Attendance, AttendanceStatus
from app.models.student import Lead
from app.models.branch import Branch
from app.routers.payments import _billing_periods

router = APIRouter(prefix="/reports", tags=["reports"])

_MONTH_UZ_SHORT = ["Yan", "Fev", "Mar", "Apr", "May", "Iyn", "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek"]


@router.get("/stats")
async def get_report_stats(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("reports", "view")),
):
    today = date.today()
    _branch_uuid: Optional[uuid.UUID] = None
    if branch_id:
        try:
            _branch_uuid = uuid.UUID(branch_id)
        except ValueError:
            pass

    # ── a) monthly_revenue — last 6 months ──────────────────────────────────
    monthly_revenue = []
    try:
        for i in range(5, -1, -1):
            offset = today.month - 1 - i
            y = today.year + offset // 12
            m = offset % 12 + 1
            m_start = date(y, m, 1)
            m_end = date(y, m, calendar.monthrange(y, m)[1])

            q = select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.date >= m_start, Payment.date <= m_end
            )
            if _branch_uuid:
                q = q.join(Group, Group.id == Payment.group_id).where(
                    Group.branch_id == _branch_uuid
                )

            total = (await db.execute(q)).scalar_one()
            monthly_revenue.append({
                "month": _MONTH_UZ_SHORT[m - 1],
                "revenue": round(int(total) / 1_000_000, 1),
            })
    except Exception:
        monthly_revenue = []

    # ── b) revenue_by_course — top 5 ────────────────────────────────────────
    revenue_by_course = []
    try:
        q = (
            select(
                Course.title.label("name"),
                func.coalesce(func.sum(Payment.amount), 0).label("total"),
            )
            .join(Group, Group.id == Payment.group_id)
            .join(Course, Course.id == Group.course_id)
        )
        if _branch_uuid:
            q = q.where(Group.branch_id == _branch_uuid)
        q = q.group_by(Course.title).order_by(func.sum(Payment.amount).desc()).limit(5)
        rows = (await db.execute(q)).all()
        COLORS = ["#4f46e5", "#10b981", "#f59e0b", "#3b82f6", "#8b5cf6"]
        revenue_by_course = [
            {"name": r.name, "value": round(int(r.total) / 1_000_000, 1), "color": COLORS[i]}
            for i, r in enumerate(rows)
        ]
    except Exception:
        revenue_by_course = []

    # ── c) enrollment_trend — last 6 months ─────────────────────────────────
    enrollment_trend = []
    try:
        for i in range(5, -1, -1):
            offset = today.month - 1 - i
            y = today.year + offset // 12
            m = offset % 12 + 1
            m_start = date(y, m, 1)
            m_end = date(y, m, calendar.monthrange(y, m)[1])

            q = (
                select(func.count(GroupStudent.id))
                .join(Group, Group.id == GroupStudent.group_id)
            )
            if _branch_uuid:
                q = q.where(Group.branch_id == _branch_uuid)
            # GroupStudent has no created_at, use group start_date as proxy
            # Fall back to counting all students in groups started that month
            q = q.where(Group.start_date >= m_start, Group.start_date <= m_end)
            cnt = (await db.execute(q)).scalar_one()
            enrollment_trend.append({"month": _MONTH_UZ_SHORT[m - 1], "value": int(cnt)})
    except Exception:
        enrollment_trend = []

    # ── d) lifecycle_funnel ──────────────────────────────────────────────────
    lifecycle_funnel = []
    try:
        leads_count = (await db.execute(select(func.count(Lead.id)))).scalar_one()

        active_q = select(func.count(User.id)).where(
            User.role == UserRole.student, User.student_status == "active"
        )
        inactive_q = select(func.count(User.id)).where(
            User.role == UserRole.student, User.student_status == "inactive"
        )
        total_students_q = select(func.count(User.id)).where(User.role == UserRole.student)

        active_cnt = (await db.execute(active_q)).scalar_one()
        inactive_cnt = (await db.execute(inactive_q)).scalar_one()
        total_cnt = (await db.execute(total_students_q)).scalar_one()
        enrolled_cnt = total_cnt - inactive_cnt

        lifecycle_funnel = [
            {"stage": "Lead",      "count": int(leads_count), "color": "#94a3b8"},
            {"stage": "Enrolled",  "count": int(enrolled_cnt), "color": "#4f46e5"},
            {"stage": "Active",    "count": int(active_cnt), "color": "#10b981"},
            {"stage": "Inactive",  "count": int(inactive_cnt), "color": "#ef4444"},
        ]
    except Exception:
        lifecycle_funnel = []

    # ── e) attendance_heatmap — per group per day of week ───────────────────
    attendance_heatmap = {}
    try:
        # Get active groups (filtered by branch)
        group_q = select(Group.id, Group.name).where(Group.status == GroupStatus.active)
        if _branch_uuid:
            group_q = group_q.where(Group.branch_id == _branch_uuid)
        group_rows = (await db.execute(group_q)).all()

        if group_rows:
            group_ids = [r.id for r in group_rows]
            # Last 60 days of attendance
            window_start = today - timedelta(days=60)

            att_rows = (await db.execute(
                select(
                    Attendance.group_id,
                    func.extract("dow", Attendance.date).label("dow"),
                    func.count(Attendance.id).label("total"),
                    func.sum(case(
                        (Attendance.status.in_([
                            AttendanceStatus.present,
                            AttendanceStatus.online,
                            AttendanceStatus.late,
                        ]), 1),
                        else_=0,
                    )).label("present"),
                )
                .where(
                    Attendance.group_id.in_(group_ids),
                    Attendance.date >= window_start,
                )
                .group_by(Attendance.group_id, func.extract("dow", Attendance.date))
            )).all()

            # dow: postgres extract("dow") = 0=Sun,1=Mon,...,6=Sat → remap to Mon=0..Sat=5
            def _dow_to_idx(dow_val):
                # postgres: 0=Sun,1=Mon..6=Sat; we want Mon=0,Tue=1,...Sat=5
                d = int(dow_val)
                return (d - 1) % 7  # Sun→6, Mon→0, ..., Sat→5

            group_name_map = {r.id: r.name for r in group_rows}
            # Build per-group, per-slot aggregations
            slot_data: dict = {}  # group_id → {slot_idx: (total, present)}
            for r in att_rows:
                gid = r.group_id
                slot = _dow_to_idx(r.dow)
                if slot >= 6:  # skip Sunday
                    continue
                if gid not in slot_data:
                    slot_data[gid] = {}
                slot_data[gid][slot] = (int(r.total), int(r.present or 0))

            for gid, gname in group_name_map.items():
                slots = slot_data.get(gid, {})
                row = []
                for s in range(6):
                    total, present = slots.get(s, (0, 0))
                    pct = round(present / total * 100) if total > 0 else 0
                    row.append(pct)
                attendance_heatmap[gname] = row
    except Exception:
        attendance_heatmap = {}

    # ── f) teacher_stats ─────────────────────────────────────────────────────
    teacher_stats = []
    try:
        teacher_q = (
            select(User.id, User.full_name)
            .join(Group, Group.teacher_id == User.id)
            .where(User.role == UserRole.teacher, Group.status == GroupStatus.active)
        )
        if _branch_uuid:
            teacher_q = teacher_q.where(Group.branch_id == _branch_uuid)
        teacher_q = teacher_q.distinct()
        teacher_rows = (await db.execute(teacher_q)).all()

        churn_window = today - timedelta(days=30)
        for t in teacher_rows:
            # Count groups
            gcount_q = select(func.count(Group.id)).where(
                Group.teacher_id == t.id, Group.status == GroupStatus.active
            )
            if _branch_uuid:
                gcount_q = gcount_q.where(Group.branch_id == _branch_uuid)
            gcount = (await db.execute(gcount_q)).scalar_one()

            # Count students
            scount_q = (
                select(func.count(GroupStudent.id))
                .join(Group, Group.id == GroupStudent.group_id)
                .where(Group.teacher_id == t.id, Group.status == GroupStatus.active)
            )
            if _branch_uuid:
                scount_q = scount_q.where(Group.branch_id == _branch_uuid)
            scount = (await db.execute(scount_q)).scalar_one()

            # Avg attendance for teacher's groups
            att_q = (
                select(
                    func.count(Attendance.id).label("total"),
                    func.sum(case(
                        (Attendance.status.in_([
                            AttendanceStatus.present,
                            AttendanceStatus.online,
                            AttendanceStatus.late,
                        ]), 1),
                        else_=0,
                    )).label("present"),
                )
                .join(Group, Group.id == Attendance.group_id)
                .where(Group.teacher_id == t.id, Attendance.date >= churn_window)
            )
            att_r = (await db.execute(att_q)).one()
            att_pct = round(int(att_r.present or 0) / int(att_r.total) * 100) if att_r.total else 0

            teacher_stats.append({
                "key": str(t.id),
                "name": t.full_name,
                "groups": int(gcount),
                "students": int(scount),
                "attendance": att_pct,
                "avgGrade": 0,
                "churn": "—",
                "nps": 0,
                "score": att_pct,
            })
    except Exception:
        teacher_stats = []

    # ── g) branch_stats — all branches ───────────────────────────────────────
    branch_stats = []
    try:
        branch_rows = (await db.execute(select(Branch).where(Branch.is_active == True))).scalars().all()
        for b in branch_rows:
            # Student count
            sc = (await db.execute(
                select(func.count(GroupStudent.id))
                .join(Group, Group.id == GroupStudent.group_id)
                .where(Group.branch_id == b.id, Group.status == GroupStatus.active)
            )).scalar_one()

            # Revenue (all time)
            rev = (await db.execute(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .join(Group, Group.id == Payment.group_id)
                .where(Group.branch_id == b.id)
            )).scalar_one()

            # Avg attendance last 30 days
            att_r = (await db.execute(
                select(
                    func.count(Attendance.id).label("total"),
                    func.sum(case(
                        (Attendance.status.in_([
                            AttendanceStatus.present,
                            AttendanceStatus.online,
                            AttendanceStatus.late,
                        ]), 1),
                        else_=0,
                    )).label("present"),
                )
                .join(Group, Group.id == Attendance.group_id)
                .where(Group.branch_id == b.id, Attendance.date >= today - timedelta(days=30))
            )).one()
            att_pct = round(int(att_r.present or 0) / int(att_r.total) * 100) if att_r.total else 0

            branch_stats.append({
                "key": str(b.id),
                "name": b.name,
                "students": int(sc),
                "revenue": f"{int(rev):,}",
                "attendance": att_pct,
                "teachers": 0,
                "score": att_pct,
            })
    except Exception:
        branch_stats = []

    # ── h) churn_risk — top 10 ───────────────────────────────────────────────
    churn_risk = []
    try:
        churn_window = today - timedelta(days=30)

        _gs_where = [Group.status == GroupStatus.active]
        if _branch_uuid:
            _gs_where.append(Group.branch_id == _branch_uuid)

        gs_rows = (await db.execute(
            select(GroupStudent, Group, User)
            .join(Group, Group.id == GroupStudent.group_id)
            .join(User, User.id == GroupStudent.student_id)
            .where(*_gs_where)
        )).all()

        if gs_rows:
            all_student_ids = list({gs.student_id for gs, _, _ in gs_rows})
            all_group_ids = list({grp.id for _, grp, _ in gs_rows})

            # Paid map
            paid_map: dict = {}
            paid_rows = (await db.execute(
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
            )).all()
            for r in paid_rows:
                paid_map[(str(r.student_id), str(r.group_id))] = int(r.total_paid)

            # Refund map
            refund_map: dict = {}
            refund_rows = (await db.execute(
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
            )).all()
            for r in refund_rows:
                refund_map[(str(r.student_id), str(r.group_id))] = int(r.total_refunded)

            # Attendance map
            att_stats = (await db.execute(
                select(
                    Attendance.student_id,
                    func.count(Attendance.id).label("total"),
                    func.sum(case(
                        (Attendance.status.in_([
                            AttendanceStatus.present,
                            AttendanceStatus.online,
                            AttendanceStatus.late,
                        ]), 1),
                        else_=0,
                    )).label("present"),
                )
                .where(Attendance.date >= churn_window, Attendance.date <= today)
                .group_by(Attendance.student_id)
            )).all()
            att_map = {str(r.student_id): (int(r.total), int(r.present or 0)) for r in att_stats}

            # Last seen map
            last_seen_rows = (await db.execute(
                select(Attendance.student_id, func.max(Attendance.date).label("last_date"))
                .where(Attendance.student_id.in_(all_student_ids))
                .group_by(Attendance.student_id)
            )).all()
            last_seen_map = {str(r.student_id): r.last_date for r in last_seen_rows}

            churn_candidates = []
            for gs, grp, student in gs_rows:
                sid_str = str(gs.student_id)
                gid_str = str(grp.id)

                total_att, present_att = att_map.get(sid_str, (0, 0))
                att_pct = round(present_att / total_att * 100) if total_att > 0 else None

                has_debt = False
                payment_start = grp.payment_start_date
                if payment_start and today >= payment_start:
                    pd_day = max(1, min(28, grp.payment_day or 1))
                    periods = _billing_periods(payment_start, pd_day, today)
                    if periods > 0:
                        price = grp.price or 0
                        first_price = grp.first_month_price if grp.first_month_price is not None else price
                        total_owed = first_price + price * (periods - 1) if periods > 1 else first_price
                        net_paid = paid_map.get((sid_str, gid_str), 0) - refund_map.get((sid_str, gid_str), 0)
                        has_debt = net_paid < total_owed

                if att_pct is not None and att_pct >= 80 and not has_debt:
                    continue
                if att_pct is None and not has_debt:
                    continue

                risk = 0
                if att_pct is not None and att_pct < 80:
                    risk += int((80 - att_pct) * 1.2)
                if has_debt:
                    risk += 35
                if att_pct is not None and att_pct < 60:
                    risk += 15
                risk = min(risk, 99)

                if risk >= 40:
                    last_date = last_seen_map.get(sid_str)
                    if last_date:
                        days_ago = (today - last_date).days
                        last_seen_str = f"{days_ago} kun oldin"
                    else:
                        last_seen_str = "Noma'lum"

                    churn_candidates.append({
                        "key": sid_str,
                        "name": student.full_name,
                        "course": grp.name,
                        "risk": risk,
                        "lastSeen": last_seen_str,
                    })

            churn_candidates.sort(key=lambda x: x["risk"], reverse=True)
            churn_risk = churn_candidates[:10]
    except Exception:
        churn_risk = []

    # ── i) payment_methods breakdown ─────────────────────────────────────────
    payment_methods = []
    try:
        from app.models.payment import PaymentMethod
        METHOD_LABELS = {
            "cash": "Naqd pul",
            "card": "Karta",
            "transfer": "O'tkazma",
        }
        METHOD_COLORS = {"cash": "#10b981", "card": "#3b82f6", "transfer": "#4f46e5"}
        q = select(
            Payment.method.label("method"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        )
        if _branch_uuid:
            q = q.join(Group, Group.id == Payment.group_id).where(Group.branch_id == _branch_uuid)
        q = q.group_by(Payment.method)
        rows = (await db.execute(q)).all()
        grand = sum(int(r.total) for r in rows) or 1
        payment_methods = [
            {
                "method": METHOD_LABELS.get(r.method.value if hasattr(r.method, 'value') else str(r.method), str(r.method)),
                "percent": round(int(r.total) / grand * 100),
                "color": METHOD_COLORS.get(r.method.value if hasattr(r.method, 'value') else str(r.method), "#94a3b8"),
            }
            for r in rows
        ]
    except Exception:
        payment_methods = []

    # ── j) financial_table — monthly revenue summary ──────────────────────────
    financial_table = []
    try:
        MONTH_UZ_LONG = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul","Avgust","Sentyabr","Oktyabr","Noyabr","Dekabr"]
        for i, item in enumerate(monthly_revenue):
            rev_sum = int(item["revenue"] * 1_000_000)
            financial_table.append({
                "key": i + 1,
                "month": MONTH_UZ_LONG[_MONTH_UZ_SHORT.index(item["month"])] if item["month"] in _MONTH_UZ_SHORT else item["month"],
                "revenue": f"{rev_sum:,}",
                "expenses": "—",
                "profit": f"{rev_sum:,}",
                "margin": "—",
            })
    except Exception:
        financial_table = []

    return {
        "monthly_revenue": monthly_revenue,
        "revenue_by_course": revenue_by_course,
        "enrollment_trend": enrollment_trend,
        "lifecycle_funnel": lifecycle_funnel,
        "attendance_heatmap": attendance_heatmap,
        "teacher_stats": teacher_stats,
        "branch_stats": branch_stats,
        "churn_risk": churn_risk,
        "payment_methods": payment_methods,
        "financial_table": financial_table,
    }
