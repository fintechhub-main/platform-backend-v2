"""
Staff profiles seed — python seed_staff.py
"""
import asyncio
import json
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.staff_profile import StaffProfile, StaffStatus

PROFILES = [
    dict(
        phone="+998901234569",  # teacher1
        status="active", specializations=["IT", "Matematika"], rating=4.9,
        bio="JavaScript va React bo'yicha 6 yillik tajribaga ega. Frontend va backend ishlab chiqish bo'yicha mutaxassis.",
        experience="6 yil", qualifications=["BSc Computer Science (TUIT)", "AWS Certified Developer"],
        monthly_earnings=4200000, kpi_attendance=98, kpi_results=91, kpi_loss=2,
        week_schedule=[
            {"day": "Dushanba", "lessons": ["React Advanced 09:00", "Node.js Backend 14:00"]},
            {"day": "Seshanba", "lessons": ["JS Beginners 10:00", "Vue.js Basics 15:00"]},
            {"day": "Chorshanba", "lessons": ["React Advanced 09:00", "Node.js Backend 14:00"]},
            {"day": "Payshanba", "lessons": ["JS Beginners 10:00"]},
            {"day": "Juma", "lessons": ["React Advanced 09:00", "Vue.js Basics 15:00"]},
        ],
        performance_history=[
            {"month": "Aprel", "attendance": 95, "results": 88},
            {"month": "May", "attendance": 97, "results": 90},
            {"month": "Iyun", "attendance": 98, "results": 91},
        ],
        salary_history=[
            {"month": "Aprel 2026", "amount": 3900000, "status": "paid"},
            {"month": "May 2026", "amount": 4100000, "status": "paid"},
            {"month": "Iyun 2026", "amount": 4200000, "status": "pending"},
        ],
    ),
    dict(
        phone="+998901234570",  # teacher2
        status="active", specializations=["Ingliz tili"], rating=4.8,
        bio="IELTS 8.0 sohibasi. 7 yil davomida ingliz tilini o'qitib keladi. Cambridge sertifikati bor.",
        experience="7 yil", qualifications=["IELTS 8.0", "Cambridge CELTA", "BA English Philology (NUUz)"],
        monthly_earnings=3800000, kpi_attendance=96, kpi_results=89, kpi_loss=3,
        week_schedule=[
            {"day": "Dushanba", "lessons": ["IELTS Prep 09:00", "Kids English 16:00"]},
            {"day": "Seshanba", "lessons": ["General English A2 10:00", "Kids English 15:00"]},
            {"day": "Chorshanba", "lessons": ["IELTS Prep 09:00", "Business English 14:00"]},
            {"day": "Payshanba", "lessons": ["General English A2 10:00", "Business English 14:00"]},
            {"day": "Juma", "lessons": ["IELTS Prep 09:00", "Speaking Club 17:00"]},
        ],
        performance_history=[
            {"month": "Aprel", "attendance": 94, "results": 87},
            {"month": "May", "attendance": 95, "results": 88},
            {"month": "Iyun", "attendance": 96, "results": 89},
        ],
        salary_history=[
            {"month": "Aprel 2026", "amount": 3600000, "status": "paid"},
            {"month": "May 2026", "amount": 3700000, "status": "paid"},
            {"month": "Iyun 2026", "amount": 3800000, "status": "pending"},
        ],
    ),
    dict(
        phone="+998901234571",  # teacher3
        status="active", specializations=["Matematika"], rating=4.7,
        bio="Oliy matematika va algebra bo'yicha mutaxassis. Olimpiada g'oliblarini tayyorlagan.",
        experience="5 yil", qualifications=["MSc Mathematics (NUUz)", "Olimpiada Coach Certificate"],
        monthly_earnings=3200000, kpi_attendance=94, kpi_results=85, kpi_loss=4,
        week_schedule=[
            {"day": "Dushanba", "lessons": ["Algebra Advanced 10:00"]},
            {"day": "Seshanba", "lessons": ["Matematika 9-sinf 09:00"]},
            {"day": "Chorshanba", "lessons": ["Algebra Advanced 10:00"]},
            {"day": "Payshanba", "lessons": ["Matematika 9-sinf 09:00"]},
            {"day": "Shanba", "lessons": ["Matematika 9-sinf 10:00", "Olimpiada tayyorlov 14:00"]},
        ],
        performance_history=[
            {"month": "Aprel", "attendance": 92, "results": 83},
            {"month": "May", "attendance": 93, "results": 84},
            {"month": "Iyun", "attendance": 94, "results": 85},
        ],
        salary_history=[
            {"month": "Aprel 2026", "amount": 3000000, "status": "paid"},
            {"month": "May 2026", "amount": 3100000, "status": "paid"},
            {"month": "Iyun 2026", "amount": 3200000, "status": "pending"},
        ],
    ),
    dict(
        phone="+998901234572",  # teacher4
        status="active", specializations=["Rus tili"], rating=4.6,
        bio="Rus tili va adabiyoti o'qituvchisi. Sankt-Peterburgda tahsil olgan. TORFL sertifikati sohibasi.",
        experience="8 yil", qualifications=["BA Russian Language (SPbU)", "TORFL C2"],
        monthly_earnings=3400000, kpi_attendance=93, kpi_results=86, kpi_loss=3,
        week_schedule=[
            {"day": "Dushanba", "lessons": ["Rus tili Boshlang'ich 09:00"]},
            {"day": "Seshanba", "lessons": ["Rus tili O'rta 10:00"]},
            {"day": "Chorshanba", "lessons": ["Rus tili Boshlang'ich 09:00"]},
            {"day": "Payshanba", "lessons": ["Rus tili O'rta 10:00"]},
            {"day": "Juma", "lessons": ["Rus tili Yuqori 11:00"]},
            {"day": "Shanba", "lessons": ["TORFL Prep 10:00"]},
        ],
        performance_history=[
            {"month": "Aprel", "attendance": 91, "results": 84},
            {"month": "May", "attendance": 92, "results": 85},
            {"month": "Iyun", "attendance": 93, "results": 86},
        ],
        salary_history=[
            {"month": "Aprel 2026", "amount": 3100000, "status": "paid"},
            {"month": "May 2026", "amount": 3200000, "status": "paid"},
            {"month": "Iyun 2026", "amount": 3400000, "status": "pending"},
        ],
    ),
    dict(
        phone="+998901234573",  # teacher5
        status="active", specializations=["IT"], rating=4.8,
        bio="Python va Data Science mutaxassisi. 4 yildan ortiq ML loyihalarida ishlagan.",
        experience="4 yil", qualifications=["BSc Data Science (INHA)", "Google Data Analytics Certificate"],
        monthly_earnings=4500000, kpi_attendance=97, kpi_results=90, kpi_loss=2,
        week_schedule=[
            {"day": "Dushanba", "lessons": ["Python Basics 10:00"]},
            {"day": "Seshanba", "lessons": ["Data Science Intensive 09:00"]},
            {"day": "Chorshanba", "lessons": ["Python Basics 10:00"]},
            {"day": "Payshanba", "lessons": ["Data Science Intensive 09:00"]},
            {"day": "Juma", "lessons": ["Data Science Intensive 09:00"]},
            {"day": "Shanba", "lessons": ["Machine Learning 11:00"]},
        ],
        performance_history=[
            {"month": "Aprel", "attendance": 95, "results": 88},
            {"month": "May", "attendance": 96, "results": 89},
            {"month": "Iyun", "attendance": 97, "results": 90},
        ],
        salary_history=[
            {"month": "Aprel 2026", "amount": 4200000, "status": "paid"},
            {"month": "May 2026", "amount": 4300000, "status": "paid"},
            {"month": "Iyun 2026", "amount": 4500000, "status": "pending"},
        ],
    ),
    # Staff members
    dict(
        phone="+998901234574",  # staff1 (Gulnora Hasanova)
        status="active", specializations=["Boshqaruv"], rating=4.5,
        bio="Platforma administratori. Umumiy boshqaruv va tashkiliy masalalar bilan shug'ullanadi.",
        experience="3 yil", qualifications=["BA Management", "HR Certificate"],
        monthly_earnings=3000000, kpi_attendance=95, kpi_results=88, kpi_loss=3,
        week_schedule=[],
        performance_history=[
            {"month": "Aprel", "attendance": 93, "results": 86},
            {"month": "May", "attendance": 94, "results": 87},
            {"month": "Iyun", "attendance": 95, "results": 88},
        ],
        salary_history=[
            {"month": "Aprel 2026", "amount": 2800000, "status": "paid"},
            {"month": "May 2026", "amount": 2900000, "status": "paid"},
            {"month": "Iyun 2026", "amount": 3000000, "status": "pending"},
        ],
    ),
]


async def seed_staff():
    async with AsyncSessionLocal() as db:
        count = 0
        for p in PROFILES:
            # find user by phone
            user_row = await db.execute(select(User).where(User.phone == p["phone"]))
            user = user_row.scalar_one_or_none()
            if not user:
                print(f"⚠️  User with phone {p['phone']} not found, skipping")
                continue

            # check existing profile
            existing = await db.execute(select(StaffProfile).where(StaffProfile.user_id == user.id))
            if existing.scalar_one_or_none():
                continue

            profile = StaffProfile(
                user_id=user.id,
                status=StaffStatus(p["status"]),
                specializations=json.dumps(p["specializations"], ensure_ascii=False),
                bio=p.get("bio"),
                experience=p.get("experience"),
                qualifications=json.dumps(p["qualifications"], ensure_ascii=False),
                rating=p["rating"],
                monthly_earnings=p["monthly_earnings"],
                kpi_attendance=p["kpi_attendance"],
                kpi_results=p["kpi_results"],
                kpi_loss=p["kpi_loss"],
                week_schedule=json.dumps(p["week_schedule"], ensure_ascii=False),
                performance_history=json.dumps(p["performance_history"], ensure_ascii=False),
                salary_history=json.dumps(p["salary_history"], ensure_ascii=False),
            )
            db.add(profile)
            count += 1

        await db.commit()
        print(f"✅ {count} ta staff profil qo'shildi!")


if __name__ == "__main__":
    asyncio.run(seed_staff())
