"""
Orchestrates hourly Telegram → DeepSeek → Vacancy pipeline.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.telegram_source import TelegramSource
from app.models.vacancy import Vacancy
from app.utils.telegram_fetcher import fetch_new_messages, _parse_channel_username
from app.utils.deepseek import extract_vacancy

logger = logging.getLogger(__name__)


async def run_auto_fetch(db: AsyncSession) -> dict:
    """Run for all active TelegramSources. Returns summary stats."""
    result = await db.execute(
        select(TelegramSource).where(TelegramSource.is_active == True)
    )
    sources = result.scalars().all()

    total_checked = 0
    total_created = 0

    for source in sources:
        created = await _process_source(db, source)
        total_checked += 1
        total_created += created

    return {"sources_checked": total_checked, "vacancies_created": total_created}


async def _process_source(db: AsyncSession, source: TelegramSource) -> int:
    """Process one source. Returns number of vacancies created."""
    username = _parse_channel_username(source.channel_url)
    created_count = 0

    try:
        messages = await fetch_new_messages(username, after_id=source.last_message_id or 0)
        logger.info(f"[auto_fetch] {username}: {len(messages)} yangi xabar")

        max_id = source.last_message_id or 0

        for msg in messages:
            # Check for duplicate
            dup = await db.execute(
                select(Vacancy).where(Vacancy.telegram_message_id == msg.id)
            )
            if dup.scalar_one_or_none():
                if msg.id > max_id:
                    max_id = msg.id
                continue

            # Ask DeepSeek
            vacancy_data = await extract_vacancy(msg.text)
            if not vacancy_data:
                if msg.id > max_id:
                    max_id = msg.id
                continue

            # Create vacancy
            vacancy = Vacancy(
                **vacancy_data,
                is_active=True,
                source="telegram",
                source_url=msg.url,
                telegram_message_id=msg.id,
                telegram_source_id=source.id,
            )
            db.add(vacancy)
            created_count += 1

            if msg.id > max_id:
                max_id = msg.id

        # Update source state
        source.last_message_id = max_id
        source.last_checked_at = datetime.now(timezone.utc)
        source.last_error = None
        source.vacancies_found = (source.vacancies_found or 0) + created_count
        await db.commit()

    except Exception as e:
        logger.error(f"[auto_fetch] {username} xato: {e}")
        source.last_error = str(e)[:500]
        source.last_checked_at = datetime.now(timezone.utc)
        await db.commit()

    return created_count
