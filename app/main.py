import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter

from app.config import settings
from app.database import AsyncSessionLocal as async_session
from app.routers import (
    auth, users, courses, groups, lessons, attendance, fines, vacancies,
    bookings, certificates, rooms, staff, leads, payments, coins, exams,
    homework, dashboard, permissions, discounts, group_progress, materials,
    branches, practicum, logs, reports, ai, telegram_sources, integrations,
    general_settings, events, holidays,
)
from app.routers.telegram_auth import router as telegram_auth_router, set_webhook
from app.utils.daily_attendance import run_daily_attendance
from app.dependencies import require_admin
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

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
    # Register Telegram webhook
    result = await set_webhook("https://lms-test.fintechhub.uz")
    logger.info(f"Telegram webhook: {result}")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="EduHub Platform API",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.DEBUG,
    docs_url="/docs" if settings.SHOW_DOCS else None,
    redoc_url="/redoc" if settings.SHOW_DOCS else None,
    openapi_url="/openapi.json" if settings.SHOW_DOCS else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(events.router,              prefix="/api/v1")
app.include_router(holidays.router,            prefix="/api/v1")
app.include_router(telegram_auth_router,       prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "docs": "/docs", "student_docs": "/student-docs"}


# ── Student Swagger ─────────────────────────────────────────────────────────
# Paths accessible to student role (read their own data + actions they can take)
_STUDENT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/change-password",
    "/api/v1/users/me",
    "/api/v1/users/me/fcm-token",
    "/api/v1/users/{user_id}",
    "/api/v1/groups/my",
    "/api/v1/groups/{group_id}",
    "/api/v1/groups/{group_id}/progress",
    "/api/v1/groups/{group_id}/materials",
    "/api/v1/groups/{group_id}/students",
    "/api/v1/courses",
    "/api/v1/courses/{course_id}",
    "/api/v1/attendance",
    "/api/v1/fines",
    "/api/v1/exams",
    "/api/v1/homework",
    "/api/v1/certificates",
    "/api/v1/coins",
    "/api/v1/coins/balance/{student_id}",
    "/api/v1/events",
    "/api/v1/events/{event_id}/registrations",
    "/api/v1/events/{event_id}/register",
    "/api/v1/vacancies",
    "/api/v1/bookings",
    "/api/v1/bookings/busy-slots",
    "/api/v1/bookings/{booking_id}",
    "/api/v1/payments/debt-summary",
    "/api/v1/payments/student-month-summary",
    "/api/v1/payments/{payment_id}",
    "/api/v1/ai/chat",
    "/api/v1/ai/settings",
    "/api/v1/permissions/my",
}


@app.get("/student-openapi.json", include_in_schema=False)
async def student_openapi_schema():
    schema = app.openapi()
    student_schema = dict(schema)
    student_schema["info"] = {**schema.get("info", {}), "title": "EduHub Student API"}
    student_schema["paths"] = {
        path: ops
        for path, ops in schema.get("paths", {}).items()
        if path in _STUDENT_PATHS
    }
    return JSONResponse(content=student_schema)


@app.get("/student-docs", include_in_schema=False)
async def student_swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/student-openapi.json",
        title="EduHub Student API Docs",
    )


# Qo'lda ishga tushirish uchun (faqat admin) — SECURITY: auth talab qilinadi
@app.post("/api/v1/internal/run-daily-attendance", include_in_schema=False)
async def trigger_daily_attendance(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    count = await run_daily_attendance(db)
    return {"created": count}
