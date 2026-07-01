import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_initialized = False


def _init():
    global _initialized
    if _initialized:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        sa_path = Path(__file__).parent.parent.parent / "firebase-service-account.json"
        if not sa_path.exists():
            logger.warning("firebase-service-account.json not found — push notifications disabled")
            return

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(sa_path))
            firebase_admin.initialize_app(cred)
        _initialized = True
    except Exception as e:
        logger.error(f"Firebase init failed: {e}")


async def send_push(token: str, title: str, body: str, data: dict | None = None) -> bool:
    """Send FCM push notification. Returns True on success."""
    _init()
    if not _initialized:
        return False
    try:
        from firebase_admin import messaging
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in (data or {}).items()},
            token=token,
        )
        messaging.send(msg)
        return True
    except Exception as e:
        logger.error(f"FCM send failed: {e}")
        return False


async def send_push_multicast(tokens: list[str], title: str, body: str, data: dict | None = None) -> int:
    """Send to multiple tokens. Returns success count."""
    _init()
    if not _initialized or not tokens:
        return 0
    try:
        from firebase_admin import messaging
        msg = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in (data or {}).items()},
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(msg)
        return response.success_count
    except Exception as e:
        logger.error(f"FCM multicast failed: {e}")
        return 0
