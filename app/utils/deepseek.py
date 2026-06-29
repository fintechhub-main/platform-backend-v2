"""
DeepSeek AI integration for vacancy extraction from Telegram messages.
API key is read from AISettings DB table (managed via /api/v1/ai/settings).
"""
import json
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Siz o'quv markazi uchun vakansiyalar aniqlovchi AI assistentsiz.
Faqat ish e'lonlarini (vakansiyalarni) ajrating. Reklamalar, yangiliklar, kurslar,
chegirmalar va boshqa kontentni rad eting.

Javobni FAQAT JSON formatda bering, hech qanday izoh yozmang."""

USER_PROMPT = """Quyidagi Telegram xabarini tahlil qiling:

---
{text}
---

Agar bu ish e'loni (vakansiya) bo'lsa, quyidagi JSON qaytaring:
{{
  "is_vacancy": true,
  "title": "lavozim nomi (qisqa, aniq)",
  "department": "bo'lim yoki soha (masalan: IT, Marketing, O'qituvchi)",
  "description": "ish tavsifi (asosiy ma'lumotlar)",
  "requirements": "talablar va shartlar",
  "salary_min": null yoki minimal oylik (so'mda, faqat raqam),
  "salary_max": null yoki maksimal oylik (so'mda, faqat raqam)
}}

Agar vakansiya bo'lmasa (reklama, yangilik, kurs e'loni, boshqa):
{{"is_vacancy": false}}

Faqat JSON qaytaring."""


async def _get_deepseek_config() -> tuple[str, str]:
    """Read DeepSeek API key and model from AISettings table."""
    from app.database import AsyncSessionLocal
    from app.models.ai_settings import AISettings
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AISettings).limit(1))
        ai = result.scalar_one_or_none()
        if ai and ai.deepseek_api_key:
            return ai.deepseek_api_key, (ai.deepseek_model or "deepseek-chat")
    return "", "deepseek-chat"


async def extract_vacancy(text: str) -> Optional[dict]:
    """
    Send message text to DeepSeek and extract vacancy info.
    Returns dict with vacancy fields or None if not a vacancy / not configured.
    """
    api_key, model = await _get_deepseek_config()
    if not api_key:
        logger.warning("[deepseek] API key sozlamalarda yo'q. AI → Sozlamalar bo'limiga kiriting.")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT.format(text=text[:3000])},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            data = json.loads(content)

            if not data.get("is_vacancy"):
                return None

            return {
                "title":        data.get("title", "Noma'lum lavozim")[:200],
                "department":   data.get("department"),
                "description":  data.get("description"),
                "requirements": data.get("requirements"),
                "salary_min":   _to_int(data.get("salary_min")),
                "salary_max":   _to_int(data.get("salary_max")),
            }

    except Exception as e:
        logger.error(f"[deepseek] xato: {e}")
        return None


def _to_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None
