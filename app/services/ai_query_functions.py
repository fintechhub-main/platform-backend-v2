"""AI chat uchun xavfsiz, oldindan belgilangan so'rov funksiyalari.

AI hech qachon xom SQL yozmaydi — faqat shu yerdagi funksiyalardan birini
va uning parametrlarini tanlaydi (`ai_data_chat.py` da JSON orqali). Bu SQL
in'ektsiya va nazoratsiz ma'lumot chiqishi xavfini butunlay yo'q qiladi.

Har bir funksiya (natija_matni: str, jadval: dict|None, chart: dict|None)
qaytaradi — jadval/chart frontendda to'g'ridan-to'g'ri ko'rsatiladi.
"""
from datetime import date, timedelta, datetime
from typing import Optional

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import Attendance
from app.models.group import Group, GroupStudent
from app.models.user import User

UZ_STATUS = {"present": "Keldi", "absent": "Kelmadi", "late": "Kech qoldi", "excused": "Sababli"}


def _table(columns, rows):
    return {"columns": columns, "rows": rows}


def _bar_chart(title, labels, values, unit=""):
    return {"title": title, "labels": labels, "values": values, "unit": unit}


async def _resolve_group_ids(db: AsyncSession, group_name: Optional[str]):
    """Guruh nomi bo'yicha (qisman moslik) topadi. None -> hammasi."""
    if not group_name:
        return None
    rows = (await db.execute(
        select(Group.id).where(Group.name.ilike(f"%{group_name}%"))
    )).scalars().all()
    return list(rows)


# ── 1) Kelmagan o'quvchilar ──────────────────────────────────────────────────

async def absent_students(db: AsyncSession, target_date: str, group_name: Optional[str] = None):
    try:
        d = date.fromisoformat(target_date)
    except (ValueError, TypeError):
        d = date.today() - timedelta(days=1)

    group_ids = await _resolve_group_ids(db, group_name)
    if group_name and not group_ids:
        return f"«{group_name}» nomli guruh topilmadi.", None, None

    q = (select(Attendance, User, Group)
         .join(User, User.id == Attendance.student_id)
         .join(Group, Group.id == Attendance.group_id)
         .where(Attendance.date == d, Attendance.status == "absent"))
    if group_ids:
        q = q.where(Attendance.group_id.in_(group_ids))
    rows = (await db.execute(q.order_by(Group.name, User.full_name))).all()

    if not rows:
        scope = f" («{group_name}» guruhida)" if group_name else ""
        return f"{d.strftime('%d.%m.%Y')} kuni{scope} hech kim kelmagan holat yo'q — barchasi qatnashgan yoki davomat hali belgilanmagan.", None, None

    table = _table(["O'quvchi", "Guruh", "Telefon", "Sabab"],
                    [[u.full_name, g.name, u.phone, a.reason or "—"] for a, u, g in rows])

    by_group = {}
    for a, u, g in rows:
        by_group[g.name] = by_group.get(g.name, 0) + 1
    chart = _bar_chart(f"{d.strftime('%d.%m.%Y')} — guruh bo'yicha kelmaganlar",
                        list(by_group.keys()), list(by_group.values()), "ta")

    text = f"{d.strftime('%d.%m.%Y')} kuni jami **{len(rows)}** nafar o'quvchi kelmadi" + \
           (f" («{group_name}» guruhida)" if group_name else f", {len(by_group)} ta guruhda") + "."
    return text, table, chart


# ── 2) O'zlashtirmayotgan (past baholi) o'quvchilar ──────────────────────────

async def underperforming_students(db: AsyncSession, group_name: Optional[str] = None,
                                    threshold: float = 5.0, limit: int = 30):
    group_ids = await _resolve_group_ids(db, group_name)
    if group_name and not group_ids:
        return f"«{group_name}» nomli guruh topilmadi.", None, None

    q = (select(User.id, User.full_name, Group.name, func.avg(Attendance.grade), func.count(Attendance.id))
         .join(Attendance, Attendance.student_id == User.id)
         .join(Group, Group.id == Attendance.group_id)
         .where(Attendance.grade.isnot(None)))
    if group_ids:
        q = q.where(Attendance.group_id.in_(group_ids))
    q = q.group_by(User.id, User.full_name, Group.name).having(func.avg(Attendance.grade) < threshold)
    q = q.order_by(func.avg(Attendance.grade)).limit(limit)
    rows = (await db.execute(q)).all()

    if not rows:
        scope = f" «{group_name}» guruhida" if group_name else ""
        return f"O'rtacha bahosi {threshold} dan past{scope} o'quvchi topilmadi — hammasi yaxshi o'zlashtirmoqda! 🎉", None, None

    table = _table(["O'quvchi", "Guruh", "O'rtacha baho", "Baholar soni"],
                    [[name, g, round(float(avg), 1), cnt] for _id, name, g, avg, cnt in rows])
    chart = _bar_chart("O'rtacha baho (past dan)", [r[1] for r in rows], [round(float(r[3]), 1) for r in rows], "ball")

    text = f"O'rtacha bahosi **{threshold}** dan past **{len(rows)}** nafar o'quvchi topildi" + \
           (f" («{group_name}» guruhida)" if group_name else "") + "."
    return text, table, chart


# ── 3) Guruh ro'yxati ─────────────────────────────────────────────────────────

async def group_roster(db: AsyncSession, group_name: str):
    group_ids = await _resolve_group_ids(db, group_name)
    if not group_ids:
        return f"«{group_name}» nomli guruh topilmadi.", None, None

    rows = (await db.execute(
        select(User, Group.name)
        .join(GroupStudent, GroupStudent.student_id == User.id)
        .join(Group, Group.id == GroupStudent.group_id)
        .where(GroupStudent.group_id.in_(group_ids))
        .order_by(Group.name, User.full_name)
    )).all()

    if not rows:
        return f"«{group_name}» guruhida o'quvchi yo'q.", None, None

    table = _table(["O'quvchi", "Guruh", "Telefon"],
                    [[u.full_name, g, u.phone] for u, g in rows])
    text = f"«{group_name}» bo'yicha topilgan guruh(lar)da jami **{len(rows)}** nafar o'quvchi bor."
    return text, table, None


# ── 4) Ism bo'yicha qidiruv (profil + so'nggi davomat/baho) ──────────────────

async def student_lookup(db: AsyncSession, name: str):
    students = (await db.execute(
        select(User).where(User.role == "student", User.full_name.ilike(f"%{name}%")).limit(10)
    )).scalars().all()

    if not students:
        return f"«{name}» ismli o'quvchi topilmadi.", None, None

    if len(students) > 1:
        table = _table(["Ism", "Telefon"], [[s.full_name, s.phone] for s in students])
        return f"«{name}» bo'yicha {len(students)} ta o'quvchi topildi — aniqroq ism yozing yoki jadvaldan tanlang:", table, None

    s = students[0]
    att_rows = (await db.execute(
        select(Attendance, Group.name)
        .join(Group, Group.id == Attendance.group_id)
        .where(Attendance.student_id == s.id)
        .order_by(Attendance.date.desc()).limit(10)
    )).all()

    if not att_rows:
        return f"**{s.full_name}** ({s.phone}) — hali davomat yozuvi yo'q.", None, None

    table = _table(["Sana", "Guruh", "Holat", "Baho"],
                    [[a.date.strftime("%d.%m.%Y"), g, UZ_STATUS.get(
                        a.status.value if hasattr(a.status, "value") else str(a.status), "-"),
                      a.grade if a.grade is not None else "—"] for a, g in att_rows])

    present = sum(1 for a, _ in att_rows if (a.status.value if hasattr(a.status, "value") else a.status) == "present")
    grades = [a.grade for a, _ in att_rows if a.grade is not None]
    avg = round(sum(grades) / len(grades), 1) if grades else None
    text = (f"**{s.full_name}** ({s.phone}) — so'nggi {len(att_rows)} darsdan {present} tasida qatnashgan"
            + (f", o'rtacha baho: {avg}." if avg is not None else "."))
    return text, table, None


# ── 5) Umumiy davomat statistikasi ───────────────────────────────────────────

async def attendance_stats(db: AsyncSession, group_name: Optional[str] = None,
                           date_from: Optional[str] = None, date_to: Optional[str] = None):
    group_ids = await _resolve_group_ids(db, group_name)
    if group_name and not group_ids:
        return f"«{group_name}» nomli guruh topilmadi.", None, None

    d_to = date.fromisoformat(date_to) if date_to else date.today()
    d_from = date.fromisoformat(date_from) if date_from else d_to - timedelta(days=30)

    q = (select(Group.name, Attendance.status, func.count(Attendance.id))
         .join(Group, Group.id == Attendance.group_id)
         .where(Attendance.date >= d_from, Attendance.date <= d_to))
    if group_ids:
        q = q.where(Attendance.group_id.in_(group_ids))
    q = q.group_by(Group.name, Attendance.status)
    rows = (await db.execute(q)).all()

    if not rows:
        return f"{d_from.strftime('%d.%m')} – {d_to.strftime('%d.%m.%Y')} oralig'ida davomat yozuvi topilmadi.", None, None

    per_group = {}
    for gname, status, cnt in rows:
        s = status.value if hasattr(status, "value") else str(status)
        per_group.setdefault(gname, {"present": 0, "absent": 0, "late": 0, "excused": 0})
        per_group[gname][s] = per_group[gname].get(s, 0) + cnt

    table_rows = []
    labels, values = [], []
    for gname, counts in sorted(per_group.items()):
        total = sum(counts.values())
        pct = round(counts.get("present", 0) * 100 / total) if total else 0
        table_rows.append([gname, counts.get("present", 0), counts.get("absent", 0), f"{pct}%"])
        labels.append(gname)
        values.append(pct)

    table = _table(["Guruh", "Keldi", "Kelmadi", "Davomat %"], table_rows)
    chart = _bar_chart("Guruh bo'yicha davomat foizi", labels, values, "%")
    text = f"{d_from.strftime('%d.%m')} – {d_to.strftime('%d.%m.%Y')} oralig'idagi davomat statistikasi:"
    return text, table, chart


# ── 6) Eng yaxshi o'quvchilar ─────────────────────────────────────────────────

async def top_students(db: AsyncSession, group_name: Optional[str] = None, limit: int = 10):
    group_ids = await _resolve_group_ids(db, group_name)
    if group_name and not group_ids:
        return f"«{group_name}» nomli guruh topilmadi.", None, None

    q = (select(User.full_name, Group.name, func.avg(Attendance.grade), func.count(Attendance.id))
         .join(Attendance, Attendance.student_id == User.id)
         .join(Group, Group.id == Attendance.group_id)
         .where(Attendance.grade.isnot(None)))
    if group_ids:
        q = q.where(Attendance.group_id.in_(group_ids))
    q = q.group_by(User.id, User.full_name, Group.name).having(func.count(Attendance.id) >= 3)
    q = q.order_by(func.avg(Attendance.grade).desc()).limit(limit)
    rows = (await db.execute(q)).all()

    if not rows:
        return "Yetarli baho tarixiga ega o'quvchi topilmadi.", None, None

    table = _table(["O'quvchi", "Guruh", "O'rtacha baho", "Baholar soni"],
                    [[name, g, round(float(avg), 1), cnt] for name, g, avg, cnt in rows])
    chart = _bar_chart("Eng yaxshi o'quvchilar", [r[0] for r in rows], [round(float(r[2]), 1) for r in rows], "ball")
    text = f"Eng yuqori o'rtacha baholi **{len(rows)}** nafar o'quvchi:"
    return text, table, chart
