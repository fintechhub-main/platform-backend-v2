import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/platform_db"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost:3001"
    DEEPSEEK_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = "Malumotimbot"
    TELEGRAM_WEBHOOK_SECRET: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    SHOW_DOCS: bool = True
    DEBUG: bool = False

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
