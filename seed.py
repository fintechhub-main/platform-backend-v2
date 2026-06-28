"""
Seed script — ishga tushirish:
    python seed.py
"""
import asyncio
from datetime import date, timedelta
from app.database import AsyncSessionLocal, engine, Base
from app.models import *  # noqa
from app.utils.auth import hash_password

# ─── Data ─────────────────────────────────────────────────────────────────────

USERS = [
    # Adminlar
    dict(full_name="Super Admin",      phone="+998901234567", email="admin@eduhub.uz",        password="admin123",   role="admin"),
    dict(full_name="Aziz Karimov",     phone="+998901234568", email="aziz@eduhub.uz",          password="admin123",   role="staff"),
    # O'qituvchilar
    dict(full_name="Bobur Rahimov",    phone="+998901234569", email="bobur@eduhub.uz",         password="teacher123", role="teacher"),
    dict(full_name="Dilnoza Karimova", phone="+998901234570", email="dilnoza@eduhub.uz",       password="teacher123", role="teacher"),
    dict(full_name="Sherzod Aliyev",   phone="+998901234571", email="sherzod@eduhub.uz",       password="teacher123", role="teacher"),
    dict(full_name="Malika Yusupova",  phone="+998901234572", email="malika@eduhub.uz",        password="teacher123", role="teacher"),
    dict(full_name="Jasur Toshmatov",  phone="+998901234573", email="jasur@eduhub.uz",         password="teacher123", role="teacher"),
    # Xodimlar
    dict(full_name="Gulnora Hasanova", phone="+998901234574", email="gulnora@eduhub.uz",       password="staff123",   role="staff"),
    dict(full_name="Rustam Qodirov",   phone="+998901234575", email="rustam@eduhub.uz",        password="staff123",   role="staff"),
    dict(full_name="Nodira Umarova",   phone="+998901234576", email="nodira@eduhub.uz",        password="staff123",   role="staff"),
    # O'quvchilar
    dict(full_name="Kamol Normatov",   phone="+998901234577", email="kamol@gmail.com",         password="student123", role="student"),
    dict(full_name="Sarvinoz Xolova",  phone="+998901234578", email="sarvinoz@gmail.com",      password="student123", role="student"),
    dict(full_name="Doniyor Ergashev", phone="+998901234579", email="doniyor@gmail.com",       password="student123", role="student"),
    dict(full_name="Mohira Sultonova", phone="+998901234580", email="mohira@gmail.com",        password="student123", role="student"),
    dict(full_name="Ulugbek Razzaqov", phone="+998901234581", email="ulugbek@gmail.com",       password="student123", role="student"),
    dict(full_name="Zulfiya Mamadaliyeva", phone="+998901234582", email="zulfiya@gmail.com",   password="student123", role="student"),
    dict(full_name="Jahongir Mirzayev",phone="+998901234583", email="jahongir@gmail.com",      password="student123", role="student"),
    dict(full_name="Barno Tursunova",  phone="+998901234584", email="barno@gmail.com",         password="student123", role="student"),
]

COURSES = [
    dict(title="Python dasturlash",         description="Python asoslaridan professional darajagacha", price=1500000, duration_months=4, is_active=True),
    dict(title="Frontend (React)",          description="HTML, CSS, JS va React bilan zamonaviy UI yaratish", price=1800000, duration_months=5, is_active=True),
    dict(title="Backend (Django/FastAPI)",  description="Python web backend ishlab chiqish", price=2000000, duration_months=5, is_active=True),
    dict(title="Flutter mobile",            description="Dart va Flutter bilan cross-platform ilovalar", price=2200000, duration_months=6, is_active=True),
    dict(title="Grafik dizayn",             description="Figma, Photoshop va UI/UX asoslari", price=1200000, duration_months=3, is_active=True),
]

VACANCIES = [
    dict(title="Python dars beruvchi",      department="O'quv bo'limi", description="Python va Django bo'yicha dars berish", requirements="2+ yil tajriba, Django bilan ishlash", salary_min=3000000, salary_max=6000000, is_active=True),
    dict(title="Frontend ustoz",            department="O'quv bo'limi", description="React.js dars berish", requirements="React, TypeScript, 1+ yil tajriba", salary_min=3500000, salary_max=7000000, is_active=True),
    dict(title="Marketing menejeri",        department="Marketing",      description="SMM va reklama kampaniyalari", requirements="SMM tajribasi, ijodiy fikrlash", salary_min=2500000, salary_max=4500000, is_active=True),
    dict(title="Kassa xodimi",              department="Moliya",         description="To'lovlarni qabul qilish va hisobot", requirements="1C, Excel bilan ishlash", salary_min=2000000, salary_max=3000000, is_active=False),
]


async def seed():
    # Jadvallarni yaratish
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # ── Users ──────────────────────────────────────────────────────────────
        user_objs = {}
        for u in USERS:
            from sqlalchemy import select
            existing = await db.execute(select(User).where(User.phone == u["phone"]))
            if existing.scalar_one_or_none():
                continue
            user = User(
                full_name=u["full_name"],
                phone=u["phone"],
                email=u["email"],
                password_hash=hash_password(u["password"]),
                role=u["role"],
            )
            db.add(user)
            user_objs[u["phone"]] = user
        await db.flush()

        # fetch all created users by phone
        from sqlalchemy import select
        result = await db.execute(select(User))
        all_users = {u.phone: u for u in result.scalars().all()}

        teachers = [u for u in all_users.values() if u.role == "teacher"]
        students = [u for u in all_users.values() if u.role == "student"]

        # ── Courses ────────────────────────────────────────────────────────────
        course_objs = []
        for c in COURSES:
            existing = await db.execute(select(Course).where(Course.title == c["title"]))
            if not existing.scalar_one_or_none():
                course = Course(**c)
                db.add(course)
                course_objs.append(course)
        await db.flush()

        result = await db.execute(select(Course))
        all_courses = result.scalars().all()

        # ── Groups ─────────────────────────────────────────────────────────────
        groups_created = []
        group_names = [
            ("PY-01", 0, 0), ("PY-02", 0, 1), ("PY-03", 0, 2),
            ("FE-01", 1, 3), ("FE-02", 1, 4),
            ("BE-01", 2, 0), ("BE-02", 2, 1),
            ("FL-01", 3, 2),
        ]
        today = date.today()
        for name, course_idx, teacher_idx in group_names:
            if course_idx >= len(all_courses) or teacher_idx >= len(teachers):
                continue
            existing = await db.execute(select(Group).where(Group.name == name))
            if existing.scalar_one_or_none():
                continue
            g = Group(
                name=name,
                course_id=all_courses[course_idx].id,
                teacher_id=teachers[teacher_idx].id,
                status="active",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=90),
                schedule="Du-Cho-Ju 10:00",
                room="Xona 1",
                max_students=15,
            )
            db.add(g)
            groups_created.append(g)
        await db.flush()

        result = await db.execute(select(Group))
        all_groups = result.scalars().all()

        # ── GroupStudents ──────────────────────────────────────────────────────
        for i, student in enumerate(students):
            group = all_groups[i % len(all_groups)]
            existing = await db.execute(
                select(GroupStudent).where(GroupStudent.group_id == group.id, GroupStudent.student_id == student.id)
            )
            if not existing.scalar_one_or_none():
                db.add(GroupStudent(group_id=group.id, student_id=student.id))

        # ── Modules & Lessons ──────────────────────────────────────────────────
        if all_courses:
            course = all_courses[0]  # Python kursi
            existing_mod = await db.execute(select(Module).where(Module.course_id == course.id))
            if not existing_mod.scalar_one_or_none():
                modules_data = [
                    dict(title="Python asoslari", order=1, is_open=True),
                    dict(title="O'zgaruvchilar va ma'lumot turlari", order=2, is_open=True),
                    dict(title="Shart operatorlari", order=3, is_open=False),
                    dict(title="Tsikllar", order=4, is_open=False),
                ]
                for md in modules_data:
                    module = Module(course_id=course.id, **md)
                    db.add(module)
                await db.flush()

                result_m = await db.execute(select(Module).where(Module.course_id == course.id).order_by(Module.order))
                modules = result_m.scalars().all()

                lessons_per_module = [
                    [
                        dict(title="Python nima?", type="text", order=1, is_open=True, duration="10 min", content="# Python nima?\nPython - yuqori darajali, umumiy maqsadli dasturlash tili."),
                        dict(title="O'rnatish va sozlash", type="video", order=2, is_open=True, duration="15 min", video_url="https://example.com/video1"),
                        dict(title="Birinchi dastur", type="code", order=3, is_open=True, duration="20 min", code_lang="python", has_terminal=True),
                    ],
                    [
                        dict(title="int, float, str", type="text", order=1, is_open=True, duration="12 min"),
                        dict(title="Amaliy mashq", type="homework", order=2, is_open=True, duration="30 min", content="## Vazifa\nQuyidagi o'zgaruvchilarni aniqlang va ularni chiqaring."),
                        dict(title="Quiz: Ma'lumot turlari", type="quiz", order=3, is_open=True, duration="10 min"),
                    ],
                    [
                        dict(title="if/elif/else", type="video", order=1, is_open=False, duration="18 min", video_url="https://example.com/video2"),
                        dict(title="Amaliy: Kalkulyator", type="code", order=2, is_open=False, duration="25 min", code_lang="python", has_terminal=True),
                    ],
                    [
                        dict(title="for tsikl", type="text", order=1, is_open=False, duration="15 min"),
                        dict(title="while tsikl", type="video", order=2, is_open=False, duration="15 min"),
                        dict(title="Imtihon: 1-bo'lim", type="exam", order=3, is_open=False, duration="45 min"),
                    ],
                ]
                for mod, lessons in zip(modules, lessons_per_module):
                    for ld in lessons:
                        db.add(Lesson(module_id=mod.id, **ld))

        # ── Attendance (so'nggi 7 kun) ─────────────────────────────────────────
        if all_groups and students:
            g = all_groups[0]
            group_student_result = await db.execute(
                select(GroupStudent).where(GroupStudent.group_id == g.id)
            )
            gs_list = group_student_result.scalars().all()
            statuses = ["present", "present", "present", "late", "absent"]
            for days_ago in range(7):
                att_date = today - timedelta(days=days_ago)
                for idx, gs in enumerate(gs_list):
                    existing_att = await db.execute(
                        select(Attendance).where(Attendance.group_id == g.id, Attendance.student_id == gs.student_id, Attendance.date == att_date)
                    )
                    if not existing_att.scalar_one_or_none():
                        db.add(Attendance(
                            group_id=g.id,
                            student_id=gs.student_id,
                            date=att_date,
                            status=statuses[idx % len(statuses)],
                            grade=(idx % 5) + 1,
                        ))

        # ── Fines ─────────────────────────────────────────────────────────────
        fine_data = [
            dict(reason="Darsga kechikish",                      amount=100000, date=today - timedelta(days=13)),
            dict(reason="Hisobot topshirmaslik",                 amount=150000, date=today - timedelta(days=20)),
            dict(reason="Dars materialini kech yuborish",        amount=80000,  date=today - timedelta(days=33)),
            dict(reason="Ish tartibini buzish",                   amount=60000,  date=today - timedelta(days=16)),
            dict(reason="Belgilangan vazifani bajarmaslik",      amount=80000,  date=today - timedelta(days=29)),
        ]
        for idx, fd in enumerate(fine_data):
            person = teachers[idx % len(teachers)] if teachers else None
            if person:
                existing_fine = await db.execute(select(Fine).where(Fine.user_id == person.id, Fine.date == fd["date"]))
                if not existing_fine.scalar_one_or_none():
                    db.add(Fine(user_id=person.id, **fd))

        # ── Vacancies ─────────────────────────────────────────────────────────
        for v in VACANCIES:
            existing_v = await db.execute(select(Vacancy).where(Vacancy.title == v["title"]))
            if not existing_v.scalar_one_or_none():
                vacancy = Vacancy(**v)
                db.add(vacancy)
        await db.flush()

        result_v = await db.execute(select(Vacancy))
        all_vacancies = result_v.scalars().all()

        applicants_data = [
            dict(full_name="Abdulloh Mirzayev",  phone="+998901111001", email="a@gmail.com", status="new"),
            dict(full_name="Feruza Yodgorova",   phone="+998901111002", email="f@gmail.com", status="interview"),
            dict(full_name="Sanjar Holiqov",     phone="+998901111003", email="s@gmail.com", status="hired"),
            dict(full_name="Nozima Rashidova",   phone="+998901111004", email="n@gmail.com", status="new"),
            dict(full_name="Bekzod Tursunov",    phone="+998901111005", email="b@gmail.com", status="rejected"),
        ]
        for idx, ap in enumerate(applicants_data):
            if all_vacancies:
                v = all_vacancies[idx % len(all_vacancies)]
                existing_ap = await db.execute(select(VacancyApplicant).where(VacancyApplicant.phone == ap["phone"]))
                if not existing_ap.scalar_one_or_none():
                    db.add(VacancyApplicant(vacancy_id=v.id, **ap))

        # ── Certificates ──────────────────────────────────────────────────────
        import uuid as uuid_lib
        templates = ["classic", "modern", "minimal"]
        for idx, student in enumerate(students[:3]):
            if all_courses:
                existing_cert = await db.execute(select(Certificate).where(Certificate.student_id == student.id))
                if not existing_cert.scalar_one_or_none():
                    db.add(Certificate(
                        student_id=student.id,
                        course_id=all_courses[idx % len(all_courses)].id,
                        template=templates[idx % len(templates)],
                        issued_date=today - timedelta(days=idx * 10),
                        serial_number=f"EDU-{uuid_lib.uuid4().hex[:8].upper()}",
                    ))

        # ── Bookings ──────────────────────────────────────────────────────────
        if teachers and students:
            booking_slots = [("09:00", 0), ("10:00", 1), ("14:00", 2), ("15:00", 0), ("16:00", 1)]
            for slot, st_idx in booking_slots:
                b_date = today + timedelta(days=1)
                teacher = teachers[0]
                student = students[st_idx % len(students)]
                existing_b = await db.execute(
                    select(Booking).where(Booking.teacher_id == teacher.id, Booking.date == b_date, Booking.time_slot == slot)
                )
                if not existing_b.scalar_one_or_none():
                    db.add(Booking(
                        teacher_id=teacher.id,
                        student_id=student.id,
                        topic="Python: funksiyalar va modullar",
                        date=b_date,
                        time_slot=slot,
                        status="pending" if st_idx < 2 else "confirmed",
                    ))

        # ── Leads ─────────────────────────────────────────────────────────────
        leads_data = [
            dict(full_name="Ali Valiyev",    phone="+998901999001", status="new",       source="Instagram"),
            dict(full_name="Maftuna Ergash", phone="+998901999002", status="contacted", source="Telegram"),
            dict(full_name="Otabek Sobirov", phone="+998901999003", status="trial",     source="Referral"),
            dict(full_name="Dilrabo Nazarova",phone="+998901999004",status="enrolled",  source="Website"),
        ]
        for ld in leads_data:
            existing_l = await db.execute(select(Lead).where(Lead.phone == ld["phone"]))
            if not existing_l.scalar_one_or_none():
                lead = Lead(**(ld | {"course_id": all_courses[0].id if all_courses else None}))
                db.add(lead)

        await db.commit()
        print("✅ Seed muvaffaqiyatli tugadi!")
        print("\n📋 Login ma'lumotlari:")
        print("  Admin:     +998901234567 / admin123")
        print("  Teacher:   +998901234569 / teacher123")
        print("  Staff:     +998901234568 / admin123")
        print("  Student:   +998901234577 / student123")


if __name__ == "__main__":
    asyncio.run(seed())
