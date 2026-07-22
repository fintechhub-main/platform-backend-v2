import asyncio
import logging
import time
import traceback
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter
from app.utils.monitoring import send_alert

from app.config import settings
from app.database import AsyncSessionLocal as async_session
from app.routers import (
    auth, users, courses, groups, lessons, attendance, fines, vacancies,
    bookings, certificates, rooms, staff, leads, payments, coins, exams,
    homework, dashboard, permissions, discounts, group_progress, materials,
    branches, practicum, logs, reports, ai, telegram_sources, integrations,
    general_settings, events, holidays, notifications, shop, cards,
    book_presentations, group_projects, resume, appointments,
)
from app.routers import lesson_homework
from app.routers import ai_data_chat
from app.routers import student as student_router_mod
from app.routers.telegram_auth import router as telegram_auth_router, set_webhook
from app.utils.daily_attendance import run_daily_attendance
from app.utils.push_jobs import run_class_reminder, run_payment_reminder
from app.utils.attendance_telegram import send_daily_attendance_telegram
from app.routers import teacher_bot as teacher_bot_router_mod
from app.routers import assistant as assistant_router_mod
from app.services.teacher_bot import tb_set_webhook
from app.utils.attendance_reminder import run_attendance_reminder
from app.services.fcm import init_firebase
from app.dependencies import require_admin
from app.database import get_db
from app.redis_client import get_redis, close_redis
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


async def _attendance_reminder_job():
    async with async_session() as db:
        try:
            await run_attendance_reminder(db)
        except Exception as e:
            logger.error(f"[att_reminder] xato: {e}")


async def _attendance_telegram_job():
    async with async_session() as db:
        try:
            await send_daily_attendance_telegram(db)
        except Exception as e:
            logger.error(f"[attendance_telegram] xato: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(_daily_job, CronTrigger(hour=6, minute=0), id="daily_attendance", replace_existing=True)
    # Har soatda vakansiya yig'ish
    scheduler.add_job(_vacancy_fetch_job, CronTrigger(minute=0), id="vacancy_auto_fetch", replace_existing=True)
    scheduler.add_job(run_class_reminder, CronTrigger(minute="*/5"), id="class_reminder", replace_existing=True)
    scheduler.add_job(run_payment_reminder, CronTrigger(hour=9, minute=0), id="payment_reminder", replace_existing=True)
    # Har kuni 09:00 (Toshkent vaqti) da kechagi davomatni guruh Telegramiga yuborish
    scheduler.add_job(_attendance_telegram_job, CronTrigger(hour=9, minute=0, timezone="Asia/Tashkent"), id="attendance_telegram", replace_existing=True)
    # Dars tugagach davomat qilinmasa — ustozga eslatma (har 5 daqiqada)
    scheduler.add_job(_attendance_reminder_job, CronTrigger(minute="*/5"),
                      id="attendance_reminder", replace_existing=True)
    scheduler.start()
    init_firebase()
    logger.info("Scheduler ishga tushdi (daily_attendance 06:00, vacancy_fetch har soat, class_reminder har 5 min, payment_reminder 09:00)")
    # Redis ulanish
    await get_redis()
    logger.info("Redis ulandi")
    # Register Telegram webhook
    result = await set_webhook("https://lms-test.fintechhub.uz")
    logger.info(f"Telegram webhook: {result}")
    tb_res = await tb_set_webhook("https://lms-test.fintechhub.uz")
    logger.info(f"Teacher bot webhook: {tb_res}")
    await send_alert("✅ <b>EduHub backend ishga tushdi</b>\nlms-test.fintechhub.uz")
    yield
    scheduler.shutdown()
    await close_redis()
    await send_alert("⚠️ <b>EduHub backend to'xtatildi</b>")


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


class ErrorMonitorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            duration_ms = int((time.time() - start) * 1000)
            if response.status_code >= 500:
                asyncio.create_task(send_alert(
                    f"🔴 <b>500 Xato</b>\n"
                    f"<code>{request.method} {request.url.path}</code>\n"
                    f"IP: {request.client.host if request.client else '?'}\n"
                    f"Vaqt: {duration_ms}ms"
                ))
            return response
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            tb = traceback.format_exc()[-800:]
            asyncio.create_task(send_alert(
                f"💥 <b>Kutilmagan xato</b>\n"
                f"<code>{request.method} {request.url.path}</code>\n"
                f"IP: {request.client.host if request.client else '?'}\n"
                f"<pre>{tb}</pre>"
            ))
            raise


app.add_middleware(ErrorMonitorMiddleware)
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
app.include_router(lesson_homework.router, prefix="/api/v1")
app.include_router(ai_data_chat.router, prefix="/api/v1")
app.include_router(student_router_mod.router, prefix="/api/v1")
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
app.include_router(notifications.router,       prefix="/api/v1")
app.include_router(shop.router,                prefix="/api/v1")
app.include_router(cards.router,               prefix="/api/v1")
app.include_router(book_presentations.router,  prefix="/api/v1")
app.include_router(group_projects.router,      prefix="/api/v1")
app.include_router(resume.router,              prefix="/api/v1")
app.include_router(appointments.router,        prefix="/api/v1")
app.include_router(teacher_bot_router_mod.router, prefix="/api/v1")
app.include_router(assistant_router_mod.router,   prefix="/api/v1")


@app.get("/")
async def root():
    return {"status": "ok", "docs": "/docs", "student_docs": "/student-docs"}


# ── Student Swagger ─────────────────────────────────────────────────────────
# Paths accessible to student role (read their own data + actions they can take)
_STUDENT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/register",
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
    "/api/v1/coins/rules",
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
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/forgot-password/verify",
    "/api/v1/auth/forgot-password/reset",
    "/api/v1/notifications",
    "/api/v1/notifications/unread-count",
    "/api/v1/notifications/mark-all-read",
    "/api/v1/notifications/{notification_id}/mark-read",
    "/api/v1/shop/products",
    "/api/v1/shop/cart",
    "/api/v1/shop/cart/add",
    "/api/v1/shop/cart/items/{item_id}",
    "/api/v1/shop/order",
    "/api/v1/shop/orders",
    "/api/v1/cards/my",
    "/api/v1/cards/lookup",
    "/api/v1/cards/topup",
    "/api/v1/cards/transfer",
    "/api/v1/cards/transfers",
    "/api/v1/book-presentations",
    "/api/v1/book-presentations/{book_id}",
    "/api/v1/group-projects",
    "/api/v1/group-projects/{project_id}",
    "/api/v1/group-projects/{project_id}/tasks/{task_id}",
    "/api/v1/group-projects/{project_id}/tasks/{task_id}/comments",
    "/api/v1/lessons/modules",
    "/api/v1/lessons/{lesson_id}",
    "/api/v1/lessons/{lesson_id}/quiz",
    "/api/v1/lessons/{lesson_id}/homework",
    "/api/v1/lessons/homework/my/{lesson_id}",
    "/api/v1/exams/{exam_id}",
    "/api/v1/exams/{exam_id}/submit",
    "/api/v1/exams/submissions",
    "/api/v1/practicum/teams",
    "/api/v1/practicum/teams/{team_id}/tasks",
    # profile edit
    "/api/v1/users/me",
    # vacancies apply
    "/api/v1/vacancies/applicants",
    # resume/CV
    "/api/v1/resume/me",
    "/api/v1/resume/{user_id}",
    "/api/v1/resume/me/education",
    "/api/v1/resume/me/education/{edu_id}",
    "/api/v1/resume/me/work-experience",
    "/api/v1/resume/me/work-experience/{work_id}",
    "/api/v1/resume/me/leadership",
    "/api/v1/resume/me/leadership/{lead_id}",
    # appointments with teacher
    "/api/v1/appointments",
    "/api/v1/appointments/available-slots",
    "/api/v1/appointments/{appointment_id}",
    # SMS register
    "/api/v1/auth/register/send-otp",
    "/api/v1/auth/register/verify-otp",
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
