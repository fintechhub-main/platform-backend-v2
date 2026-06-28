from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, users, courses, groups, lessons, attendance, fines, vacancies, bookings, certificates, rooms, staff, leads, payments, coins, exams, homework, dashboard, permissions, discounts, group_progress, materials, branches, practicum, logs, reports, ai

app = FastAPI(title="EduHub Platform API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,         prefix="/api/v1")
app.include_router(users.router,        prefix="/api/v1")
app.include_router(courses.router,      prefix="/api/v1")
app.include_router(groups.router,       prefix="/api/v1")
app.include_router(lessons.router,      prefix="/api/v1")
app.include_router(attendance.router,   prefix="/api/v1")
app.include_router(fines.router,        prefix="/api/v1")
app.include_router(vacancies.router,    prefix="/api/v1")
app.include_router(bookings.router,     prefix="/api/v1")
app.include_router(certificates.router, prefix="/api/v1")
app.include_router(rooms.router,        prefix="/api/v1")
app.include_router(staff.router,        prefix="/api/v1")
app.include_router(leads.router,        prefix="/api/v1")
app.include_router(payments.router,     prefix="/api/v1")
app.include_router(coins.router,        prefix="/api/v1")
app.include_router(exams.router,        prefix="/api/v1")
app.include_router(homework.router,     prefix="/api/v1")
app.include_router(dashboard.router,    prefix="/api/v1")
app.include_router(permissions.router,  prefix="/api/v1")
app.include_router(discounts.router,       prefix="/api/v1")
app.include_router(group_progress.router,  prefix="/api/v1")
app.include_router(materials.router,       prefix="/api/v1")
app.include_router(branches.router,        prefix="/api/v1")
app.include_router(practicum.router,       prefix="/api/v1")
app.include_router(logs.router,            prefix="/api/v1")
app.include_router(reports.router,         prefix="/api/v1")
app.include_router(ai.router,              prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "docs": "/docs"}
