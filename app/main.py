import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal as async_session
from app.routers import (
    auth, users, courses, groups, lessons, attendance, fines, vacancies,
    bookings, certificates, rooms, staff, leads, payments, coins, exams,
    homework, dashboard, permissions, discounts, group_progress, materials,
    branches, practicum, logs, reports, ai, telegram_sources, integrations,
    general_settings,
)
from app.utils.daily_attendance import run_daily_attendance

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _daily_job():
    async with async_session() as db:
        try:
            await run_daily_attendance(db)
        except Exception as e:
            logger.error(f"[daily_attendance] xato: {e}")


async def _vacancy_fetch_job():
    from app.utils.vacancy_auto_fetch import run_auto_fetch
    async with async_session() as db:
        try:
            stats = await run_auto_fetch(db)
            logger.info(f"[vacancy_fetch] {stats}")
        except Exception as e:
            logger.error(f"[vacancy_fetch] xato: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(_daily_job, CronTrigger(hour=6, minute=0), id="daily_attendance", replace_existing=True)
    # Har soatda vakansiya yig'ish
    scheduler.add_job(_vacancy_fetch_job, CronTrigger(minute=0), id="vacancy_auto_fetch", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler ishga tushdi (daily_attendance 06:00, vacancy_fetch har soat)")
    yield
    scheduler.shutdown()


app = FastAPI(title="EduHub Platform API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,            prefix="/api/v1")
app.include_router(users.router,           prefix="/api/v1")
app.include_router(courses.router,         prefix="/api/v1")
app.include_router(groups.router,          prefix="/api/v1")
app.include_router(lessons.router,         prefix="/api/v1")
app.include_router(attendance.router,      prefix="/api/v1")
app.include_router(fines.router,           prefix="/api/v1")
app.include_router(vacancies.router,       prefix="/api/v1")
app.include_router(bookings.router,        prefix="/api/v1")
app.include_router(certificates.router,    prefix="/api/v1")
app.include_router(rooms.router,           prefix="/api/v1")
app.include_router(staff.router,           prefix="/api/v1")
app.include_router(leads.router,           prefix="/api/v1")
app.include_router(payments.router,        prefix="/api/v1")
app.include_router(coins.router,           prefix="/api/v1")
app.include_router(exams.router,           prefix="/api/v1")
app.include_router(homework.router,        prefix="/api/v1")
app.include_router(dashboard.router,       prefix="/api/v1")
app.include_router(permissions.router,     prefix="/api/v1")
app.include_router(discounts.router,       prefix="/api/v1")
app.include_router(group_progress.router,  prefix="/api/v1")
app.include_router(materials.router,       prefix="/api/v1")
app.include_router(branches.router,        prefix="/api/v1")
app.include_router(practicum.router,       prefix="/api/v1")
app.include_router(logs.router,            prefix="/api/v1")
app.include_router(reports.router,             prefix="/api/v1")
app.include_router(ai.router,                  prefix="/api/v1")
app.include_router(telegram_sources.router,    prefix="/api/v1")
app.include_router(integrations.router,        prefix="/api/v1")
app.include_router(general_settings.router,    prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "docs": "/docs"}


# Qo'lda ishga tushirish uchun (test/debug)
@app.post("/api/v1/internal/run-daily-attendance", include_in_schema=False)
async def trigger_daily_attendance():
    async with async_session() as db:
        count = await run_daily_attendance(db)
    return {"created": count}
