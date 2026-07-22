"""Barcha o'quvchilar parolini {ism_bosh_harfi}00000000 ga o'tkazadi.

Sabab: avvalgi parol tug'ilgan sanaga asoslangan edi, lekin ba'zi
o'quvchilarning tug'ilgan sanasi bazada xato ekan. Yangi parol hech qanday
boshqa maydonga bog'liq emas, shuning uchun ishonchli.

Xavfsizlik: har bir o'quvchi keyingi kirishda parolni majburiy
o'zgartirishi kerak bo'ladi (must_change_password=True).

Eski parol xeshlari tiklash/audit uchun _bak_student_pw jadvaliga saqlanadi.
"""
import asyncio
from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models.user import User
from app.utils.auth import hash_password


def gen_password(full_name: str) -> str:
    letter = (full_name or "x").strip()[:1] or "x"
    return letter.lower() + "00000000"


async def main():
    async with AsyncSessionLocal() as db:
        await db.execute(text('''
            CREATE TABLE IF NOT EXISTS _bak_student_pw (
                user_id UUID PRIMARY KEY,
                old_password_hash TEXT NOT NULL,
                backed_up_at TIMESTAMPTZ DEFAULT now()
            )
        '''))
        await db.commit()

        rows = (await db.execute(
            select(User).where(User.role == "student")
        )).scalars().all()
        print("Jami o'quvchi:", len(rows))

        done = 0
        for u in rows:
            await db.execute(text('''
                INSERT INTO _bak_student_pw (user_id, old_password_hash)
                VALUES (:uid, :old)
                ON CONFLICT (user_id) DO NOTHING
            '''), {"uid": str(u.id), "old": u.password_hash})

            pw = gen_password(u.full_name)
            u.password_hash = hash_password(pw)
            u.must_change_password = True
            u.token_version = (u.token_version or 1) + 1  # eski tokenlarni bekor qiladi

            done += 1
            if done % 50 == 0:
                await db.commit()
                print("  ", done, "/", len(rows))

        await db.commit()
        print("TUGADI:", done, "ta o'quvchi parol yangilandi")

        # Namuna tekshiruv
        sample = (await db.execute(
            select(User.full_name, User.phone).where(User.role == "student").limit(5)
        )).all()
        for name, phone in sample:
            print("  namuna:", name, "|", phone, "| parol:", gen_password(name))


asyncio.run(main())
