import httpx
from app.config import settings

_TG_API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_alert(text: str, chat_id: str | None = None) -> None:
    token = settings.MONITOR_BOT_TOKEN
    cid = chat_id or settings.MONITOR_CHAT_ID
    if not token or not cid:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                _TG_API.format(token=token),
                json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass  # monitoring xatosi asosiy jarayonni to'xtatmasin
