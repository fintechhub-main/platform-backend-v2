from app.models.user import User
from app.models.course import Course
from app.models.group import Group, GroupStudent
from app.models.lesson import Module, Lesson
from app.models.student import Lead
from app.models.attendance import Attendance
from app.models.homework import HomeworkSubmission
from app.models.exam import Exam, ExamSubmission
from app.models.fine import Fine
from app.models.vacancy import Vacancy, VacancyApplicant
from app.models.certificate import Certificate
from app.models.booking import Booking
from app.models.room import Room
from app.models.staff_profile import StaffProfile
from app.models.payment import Payment, PaymentRefund
from app.models.coin import CoinTransaction
from app.models.permission import RolePermission
from app.models.discount import Discount
from app.models.group_progress import GroupModuleAccess, GroupLessonDone
from app.models.material import GroupMaterial
from app.models.payment_log import PaymentLog
from app.models.branch import Branch
from app.models.practicum import PracticumTeam, PracticumTask
from app.models.audit_log import AuditLog
from app.models.ai_settings import AISettings
from app.models.telegram_source import TelegramSource
from app.models.integration_settings import IntegrationSettings
from app.models.general_settings import GeneralSettings

__all__ = [
    "User", "Course", "Group", "GroupStudent",
    "Module", "Lesson", "Lead",
    "Attendance", "HomeworkSubmission",
    "Exam", "ExamSubmission",
    "Fine", "Vacancy", "VacancyApplicant",
    "Certificate", "Booking", "Room", "StaffProfile",
    "Payment", "PaymentRefund", "PaymentLog", "CoinTransaction", "RolePermission",
    "Discount", "GroupModuleAccess", "GroupLessonDone",
    "Branch", "PracticumTeam", "PracticumTask",
    "AuditLog",
    "AISettings",
    "TelegramSource",
    "IntegrationSettings",
]
