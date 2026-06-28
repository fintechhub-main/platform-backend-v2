"""
Xonalar seed — python seed_rooms.py
"""
import asyncio
import json
from app.database import AsyncSessionLocal
from app.models.room import Room

ROOMS = [
    dict(code="A-101", name="Asosiy darsxona", floor="1-qavat", type="classroom", capacity=25, status="occupied",
         amenities=["wifi","projector","whiteboard"], current_group="Frontend-12", next_free="12:00",
         schedule=[{"group":"Frontend-12","from":"09:00","to":"12:00"},{"group":"React-05","from":"14:00","to":"16:00"},{"group":"JS-08","from":"17:00","to":"19:00"}],
         weekly={"Dushanba":[{"group":"Frontend-12","from":"09:00","to":"12:00"},{"group":"JS-08","from":"17:00","to":"19:00"}],"Seshanba":[{"group":"React-05","from":"14:00","to":"16:00"}],"Chorshanba":[{"group":"Frontend-12","from":"09:00","to":"12:00"},{"group":"JS-08","from":"17:00","to":"19:00"}],"Payshanba":[{"group":"React-05","from":"14:00","to":"16:00"}],"Juma":[{"group":"Frontend-12","from":"09:00","to":"12:00"}],"Shanba":[]}),
    dict(code="A-102", name="Kichik sinf", floor="1-qavat", type="classroom", capacity=15, status="available",
         amenities=["wifi","whiteboard"], current_group=None, next_free=None,
         schedule=[{"group":"Vue-03","from":"10:00","to":"12:00"},{"group":"CSS-02","from":"15:00","to":"17:00"}],
         weekly={"Dushanba":[{"group":"Vue-03","from":"10:00","to":"12:00"}],"Seshanba":[{"group":"CSS-02","from":"15:00","to":"17:00"}],"Chorshanba":[{"group":"Vue-03","from":"10:00","to":"12:00"}],"Payshanba":[{"group":"CSS-02","from":"15:00","to":"17:00"}],"Juma":[],"Shanba":[{"group":"Vue-03","from":"10:00","to":"13:00"}]}),
    dict(code="A-201", name="Multimedia xona", floor="2-qavat", type="classroom", capacity=30, status="occupied",
         amenities=["wifi","projector","camera","audio"], current_group="Python-07", next_free="14:30",
         schedule=[{"group":"Python-07","from":"09:00","to":"14:30"},{"group":"Django-01","from":"15:00","to":"17:30"}],
         weekly={"Dushanba":[{"group":"Python-07","from":"09:00","to":"12:00"}],"Seshanba":[{"group":"Django-01","from":"15:00","to":"17:30"}],"Chorshanba":[{"group":"Python-07","from":"09:00","to":"12:00"}],"Payshanba":[{"group":"Django-01","from":"15:00","to":"17:30"}],"Juma":[{"group":"Python-07","from":"09:00","to":"14:30"}],"Shanba":[]}),
    dict(code="A-202", name="Katta sinf", floor="2-qavat", type="classroom", capacity=35, status="available",
         amenities=["wifi","projector","whiteboard"], current_group=None, next_free=None,
         schedule=[{"group":"Flutter-04","from":"08:00","to":"10:00"},{"group":"Kotlin-02","from":"18:00","to":"20:00"}],
         weekly={"Dushanba":[{"group":"Flutter-04","from":"08:00","to":"10:00"}],"Seshanba":[{"group":"Kotlin-02","from":"18:00","to":"20:00"}],"Chorshanba":[{"group":"Flutter-04","from":"08:00","to":"10:00"}],"Payshanba":[{"group":"Kotlin-02","from":"18:00","to":"20:00"}],"Juma":[{"group":"Flutter-04","from":"08:00","to":"10:00"}],"Shanba":[]}),
    dict(code="B-101", name="IT laboratoriya", floor="1-qavat", type="lab", capacity=20, status="occupied",
         amenities=["wifi","computers","projector"], current_group="Backend-03", next_free="15:00",
         schedule=[{"group":"Backend-03","from":"11:00","to":"15:00"},{"group":"DevOps-01","from":"16:00","to":"18:00"}],
         weekly={"Dushanba":[{"group":"Backend-03","from":"11:00","to":"15:00"}],"Seshanba":[{"group":"DevOps-01","from":"16:00","to":"18:00"}],"Chorshanba":[{"group":"Backend-03","from":"11:00","to":"15:00"}],"Payshanba":[{"group":"DevOps-01","from":"16:00","to":"18:00"}],"Juma":[{"group":"Backend-03","from":"11:00","to":"15:00"}],"Shanba":[]}),
    dict(code="B-102", name="Kompyuter sinfi", floor="1-qavat", type="computer", capacity=20, status="available",
         amenities=["wifi","computers","projector"], current_group=None, next_free=None,
         schedule=[{"group":"DataSci-02","from":"09:00","to":"11:00"},{"group":"ML-01","from":"13:00","to":"16:00"}],
         weekly={"Dushanba":[{"group":"DataSci-02","from":"09:00","to":"11:00"}],"Seshanba":[{"group":"ML-01","from":"13:00","to":"16:00"}],"Chorshanba":[{"group":"DataSci-02","from":"09:00","to":"11:00"}],"Payshanba":[{"group":"ML-01","from":"13:00","to":"16:00"}],"Juma":[],"Shanba":[{"group":"DataSci-02","from":"10:00","to":"13:00"}]}),
    dict(code="B-201", name="Dizayn studiyasi", floor="2-qavat", type="lab", capacity=16, status="repair",
         amenities=["wifi","computers"], current_group=None, next_free="Erta",
         schedule=[], weekly={"Dushanba":[],"Seshanba":[],"Chorshanba":[],"Payshanba":[],"Juma":[],"Shanba":[]}),
    dict(code="C-101", name="Konferens-zal", floor="1-qavat", type="conference", capacity=50, status="available",
         amenities=["wifi","projector","camera","audio","whiteboard"], current_group=None, next_free=None,
         schedule=[{"group":"Yig'ilish","from":"14:00","to":"16:00"}],
         weekly={"Dushanba":[{"group":"Yig'ilish","from":"14:00","to":"16:00"}],"Seshanba":[],"Chorshanba":[{"group":"Prezentatsiya","from":"11:00","to":"13:00"}],"Payshanba":[],"Juma":[{"group":"Yig'ilish","from":"14:00","to":"16:00"}],"Shanba":[]}),
    dict(code="C-201", name="Katta auditoriya", floor="2-qavat", type="conference", capacity=80, status="occupied",
         amenities=["wifi","projector","camera","audio"], current_group="Umumiy yig'ilish", next_free="16:00",
         schedule=[{"group":"Umumiy yig'ilish","from":"10:00","to":"16:00"},{"group":"Taqdimot","from":"17:00","to":"19:00"}],
         weekly={"Dushanba":[{"group":"Umumiy yig'ilish","from":"10:00","to":"13:00"}],"Seshanba":[],"Chorshanba":[{"group":"Taqdimot","from":"17:00","to":"19:00"}],"Payshanba":[{"group":"Umumiy yig'ilish","from":"10:00","to":"13:00"}],"Juma":[],"Shanba":[{"group":"Ochiq dars","from":"09:00","to":"12:00"}]}),
    dict(code="A-301", name="VIP klass", floor="3-qavat", type="classroom", capacity=12, status="available",
         amenities=["wifi","projector","camera","whiteboard"], current_group=None, next_free=None,
         schedule=[{"group":"IELTS-Prep","from":"08:00","to":"10:00"}],
         weekly={"Dushanba":[{"group":"IELTS-Prep","from":"08:00","to":"10:00"}],"Seshanba":[{"group":"IELTS-Prep","from":"08:00","to":"10:00"}],"Chorshanba":[{"group":"IELTS-Prep","from":"08:00","to":"10:00"}],"Payshanba":[],"Juma":[{"group":"IELTS-Prep","from":"08:00","to":"10:00"}],"Shanba":[]}),
    dict(code="B-301", name="3D laboratoriya", floor="3-qavat", type="lab", capacity=10, status="closed",
         amenities=["wifi","computers"], current_group=None, next_free=None,
         schedule=[], weekly={"Dushanba":[],"Seshanba":[],"Chorshanba":[],"Payshanba":[],"Juma":[],"Shanba":[]}),
    dict(code="A-103", name="Sinov xonasi", floor="1-qavat", type="classroom", capacity=20, status="available",
         amenities=["wifi","whiteboard"], current_group=None, next_free=None,
         schedule=[{"group":"Imtihon-1","from":"09:00","to":"11:00"},{"group":"Imtihon-2","from":"14:00","to":"16:00"}],
         weekly={"Dushanba":[{"group":"Imtihon-1","from":"09:00","to":"11:00"}],"Seshanba":[],"Chorshanba":[{"group":"Imtihon-2","from":"14:00","to":"16:00"}],"Payshanba":[],"Juma":[{"group":"Yakuniy test","from":"10:00","to":"12:00"}],"Shanba":[]}),
]


async def seed_rooms():
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        for r in ROOMS:
            existing = await db.execute(select(Room).where(Room.code == r["code"]))
            if existing.scalar_one_or_none():
                continue
            room = Room(
                code=r["code"],
                name=r["name"],
                floor=r["floor"],
                type=r["type"],
                capacity=r["capacity"],
                status=r["status"],
                amenities=json.dumps(r["amenities"], ensure_ascii=False),
                current_group=r.get("current_group"),
                next_free=r.get("next_free"),
                schedule=json.dumps(r["schedule"], ensure_ascii=False),
                weekly=json.dumps(r["weekly"], ensure_ascii=False),
            )
            db.add(room)
        await db.commit()
        print(f"✅ {len(ROOMS)} ta xona qo'shildi!")


if __name__ == "__main__":
    asyncio.run(seed_rooms())
