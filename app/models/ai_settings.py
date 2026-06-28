import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID as SAUUID, JSONB

from app.database import Base


class AISettings(Base):
    __tablename__ = "ai_settings"

    id: Mapped[uuid.UUID] = mapped_column(SAUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), default="openai")  # openai|gemini|claude|deepseek
    openai_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    openai_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    gemini_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_model: Mapped[str] = mapped_column(String(100), default="gemini-1.5-flash")
    claude_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    claude_model: Mapped[str] = mapped_column(String(100), default="claude-haiku-4-5-20251001")
    deepseek_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    deepseek_model: Mapped[str] = mapped_column(String(100), default="deepseek-chat")
    token_budget: Mapped[int] = mapped_column(Integer, default=1000000)
    enabled_modules: Mapped[dict] = mapped_column(JSONB, default=lambda: {
        "grading": True, "chatbot": True, "analytics": True,
        "summary": True, "plagiarism": False, "recommendations": True
    })
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
