import os
import logging
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)
_initialized = False


def init_firebase():
    global _initialized
    if _initialized:
        return
    try:
        cred_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "firebase-service-account.json"
        )
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info("Firebase Admin SDK initialized")
    except Exception as e:
        logger.error(f"Firebase init error: {e}")


def send_push(token: str, title: str, body: str, data: dict = None) -> bool:
    if not token or not _initialized:
        return False
    try:
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default")
                )
            ),
        )
        messaging.send(msg)
        return True
    except Exception as e:
        logger.warning(f"FCM send error (token={token[:20]}...): {e}")
        return False


def send_push_multicast(tokens: list[str], title: str, body: str, data: dict = None) -> int:
    """Send to multiple tokens, returns success count."""
    if not tokens or not _initialized:
        return 0
    clean = [t for t in tokens if t]
    if not clean:
        return 0
    try:
        msg = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            tokens=clean,
            android=messaging.AndroidConfig(priority="high"),
        )
        resp = messaging.send_each_for_multicast(msg)
        return resp.success_count
    except Exception as e:
        logger.warning(f"FCM multicast error: {e}")
        return 0
